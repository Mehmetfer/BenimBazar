"""Paribu public WebSocket client — reconnect, timeout, malformed-safe."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger("borsa_bot.crypto.ws")

PUBLIC_WS_URL = "wss://api.paribu.com/v1/wapi/stream"


@dataclass
class BookTop:
    bid: float | None = None
    ask: float | None = None
    seq: int | None = None
    updated_at: datetime | None = None


@dataclass
class WSState:
    connected: bool = False
    last_message_at: float | None = None
    last_error: str = ""
    reconnects: int = 0
    subscribed: list[str] = field(default_factory=list)


class ParibuPublicStream:
    """Background public stream. Optional dependency: websocket-client.

    On missing library or failure → connected=False (caller uses HTTP polling).
    """

    def __init__(
        self,
        *,
        url: str = PUBLIC_WS_URL,
        on_match_price: Callable[[str, float, datetime], None] | None = None,
        on_match: Callable[[str, float, float, datetime], None] | None = None,
        on_book_top: Callable[[str, float, float, datetime], None] | None = None,
        reconnect_sec: float = 3.0,
    ) -> None:
        self.url = url
        self.on_match_price = on_match_price
        self.on_match = on_match
        self.on_book_top = on_book_top
        self.reconnect_sec = reconnect_sec
        self.state = WSState()
        self._channels: list[str] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ws = None
        self._book_seq: dict[str, int] = {}
        self.book_tops: dict[str, BookTop] = {}

    def set_channels(self, channels: list[str]) -> None:
        self._channels = list(channels)
        self.state.subscribed = list(channels)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="paribu-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:  # noqa: BLE001
            pass

    def _run_loop(self) -> None:
        try:
            import websocket  # type: ignore
        except ImportError:
            self.state.last_error = "websocket-client not installed — HTTP polling only"
            self.state.connected = False
            log.warning(self.state.last_error)
            return

        while not self._stop.is_set():
            try:
                self._connect_once(websocket)
            except Exception as exc:  # noqa: BLE001
                self.state.connected = False
                self.state.last_error = str(exc)
                log.warning("paribu ws error: %s", exc)
            if self._stop.is_set():
                break
            self.state.reconnects += 1
            time.sleep(self.reconnect_sec)

    def _connect_once(self, websocket: Any) -> None:
        done = threading.Event()

        def on_open(ws: Any) -> None:
            self.state.connected = True
            self.state.last_error = ""
            if self._channels:
                payload = {"method": "subscribe", "channels": self._channels, "id": f"sub_{int(time.time())}"}
                ws.send(json.dumps(payload))

        def on_message(_ws: Any, message: str) -> None:
            self.state.last_message_at = time.time()
            self._handle_message(message)

        def on_error(_ws: Any, error: Any) -> None:
            self.state.last_error = str(error)
            self.state.connected = False

        def on_close(_ws: Any, status: Any, msg: Any) -> None:
            self.state.connected = False
            # 4003 → gap; always reconnect+resubscribe per docs
            if status == 4003:
                self.state.last_error = "orderbook gap 4003 — resubscribe"
            done.set()

        self._ws = websocket.WebSocketApp(
            self.url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        # ping_interval aligns with ~20s server ping guidance
        self._ws.run_forever(ping_interval=20, ping_timeout=25)
        done.wait(timeout=0.1)

    def _handle_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            self.state.last_error = "malformed JSON"
            return
        if not isinstance(payload, dict):
            return
        # status / errors
        if payload.get("e") == "status":
            r = payload.get("r") or {}
            if isinstance(r, dict) and r.get("t") == "error":
                self.state.last_error = str(r.get("msg") or "ws error")
            return

        market = str(payload.get("s") or "").lower()
        r = payload.get("r") or {}
        if not isinstance(r, dict):
            return
        kind = r.get("t")
        event_ms = payload.get("E") or r.get("T")
        try:
            ts = (
                datetime.fromtimestamp(float(event_ms) / 1000.0, tz=timezone.utc)
                if event_ms is not None
                else datetime.now(timezone.utc)
            )
        except (TypeError, ValueError):
            ts = datetime.now(timezone.utc)

        if kind == "match-price" and self.on_match_price and market:
            try:
                price = float(r["p"])
            except (KeyError, TypeError, ValueError):
                return
            self.on_match_price(market, price, ts)
            return

        if kind == "match" and self.on_match and market:
            try:
                price = float(r["p"])
                qty = float(r["q"])
            except (KeyError, TypeError, ValueError):
                return
            self.on_match(market, price, qty, ts)
            return

        if kind in {"snapshot", "diff"} and market:
            self._apply_book(market, r, ts)

    def _apply_book(self, market: str, r: dict[str, Any], ts: datetime) -> None:
        top = self.book_tops.get(market) or BookTop()
        kind = r.get("t")
        sq = r.get("sq")
        try:
            sq_i = int(sq) if sq is not None else None
        except (TypeError, ValueError):
            sq_i = None

        if kind == "snapshot":
            bids = r.get("b") or []
            asks = r.get("a") or []
            try:
                if bids:
                    top.bid = float(bids[0][0])
                if asks:
                    top.ask = float(asks[0][0])
            except (TypeError, ValueError, IndexError):
                return
            top.seq = sq_i
            self._book_seq[market] = sq_i if sq_i is not None else 0
        elif kind == "diff":
            local = self._book_seq.get(market)
            if local is not None and sq_i is not None and sq_i > local + 1:
                # gap — close handled by server; mark error for resubscribe path
                self.state.last_error = f"book gap local={local} sq={sq_i}"
                try:
                    if self._ws:
                        self._ws.close()
                except Exception:  # noqa: BLE001
                    pass
                return
            bids = r.get("b") or []
            asks = r.get("a") or []
            # For top-of-book only: if first level present, update
            try:
                if bids and float(bids[0][1]) > 0:
                    top.bid = float(bids[0][0])
                if asks and float(asks[0][1]) > 0:
                    top.ask = float(asks[0][0])
            except (TypeError, ValueError, IndexError):
                pass
            if sq_i is not None:
                self._book_seq[market] = sq_i
                top.seq = sq_i
        top.updated_at = ts
        self.book_tops[market] = top
        if self.on_book_top and top.bid and top.ask:
            self.on_book_top(market, top.bid, top.ask, ts)
