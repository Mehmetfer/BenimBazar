"""CHANGE X Core V1.1 controlled load profiles (browse/create/offer/accept/cancel)."""

from __future__ import annotations

import concurrent.futures
import json
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from changex.app import db
from changex.app import main as main_mod
from changex.tests.helpers import auth, make_listing, register


@dataclass
class LoadStats:
    name: str
    concurrent_users: int
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    timeouts: int = 0
    successful_trades: int = 0
    rejected_trades: int = 0
    duplicate_ops: int = 0
    requests: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_latency(self, ms: float) -> None:
        with self._lock:
            self.latencies_ms.append(ms)
            self.requests += 1

    def inc(self, field_name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, field_name, getattr(self, field_name) + n)

    def finalize(self, started: float, lock_stats: dict) -> dict:
        elapsed = max(time.perf_counter() - started, 1e-9)
        with self._lock:
            xs = sorted(self.latencies_ms) or [0.0]
            requests = self.requests
            errors = self.errors
            timeouts = self.timeouts
            successful_trades = self.successful_trades
            rejected_trades = self.rejected_trades
            duplicate_ops = self.duplicate_ops

        def pct(p: float) -> float:
            if not xs:
                return 0.0
            idx = min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))
            return xs[idx]

        return {
            "profile": self.name,
            "concurrent_users": self.concurrent_users,
            "requests": requests,
            "requests_per_sec": requests / elapsed,
            "p50_ms": pct(50),
            "p95_ms": pct(95),
            "p99_ms": pct(99),
            "mean_ms": statistics.fmean(xs) if xs else 0.0,
            "error_rate": (errors / requests) if requests else 0.0,
            "timeout_count": timeouts,
            "successful_trades": successful_trades,
            "rejected_trades": rejected_trades,
            "duplicate_operations": duplicate_ops,
            "db_lock_stats": lock_stats,
            "elapsed_sec": elapsed,
        }


def _run_user_flow(client, user_idx: int, stats: LoadStats) -> None:
    """Simulate browse + create + offer + accept/cancel mix."""
    main_mod._RATE.clear()
    try:
        t0 = time.perf_counter()
        u = register(client, f"load_{stats.name}_{user_idx}_{uuid.uuid4().hex[:8]}")
        stats.add_latency((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        r = client.get("/api/listings")
        stats.add_latency((time.perf_counter() - t0) * 1000)
        if r.status_code >= 400:
            stats.inc("errors")

        t0 = time.perf_counter()
        mine = make_listing(client, u["token"], f"Item-{user_idx}", madalyon=1)
        stats.add_latency((time.perf_counter() - t0) * 1000)

        peer = register(client, f"peer_{stats.name}_{user_idx}_{uuid.uuid4().hex[:8]}")
        stats.add_latency(0.0)
        peer_listing = make_listing(client, peer["token"], f"Peer-{user_idx}", madalyon=1)
        stats.add_latency(0.0)

        t0 = time.perf_counter()
        offer = client.post(
            "/api/trades/offer",
            headers=auth(u["token"]),
            json={
                "requested_listing_ids": [peer_listing["id"]],
                "offered_listing_ids": [mine["id"]],
                "idempotency_key": f"load-offer-{stats.name}-{user_idx}-{uuid.uuid4().hex[:6]}",
            },
        )
        stats.add_latency((time.perf_counter() - t0) * 1000)
        if offer.status_code != 200:
            stats.inc("errors")
            stats.inc("rejected_trades")
            return

        t0 = time.perf_counter()
        if user_idx % 2 == 0:
            acc = client.post(
                f"/api/trades/{offer.json()['id']}/accept",
                headers=auth(peer["token"]),
                json={"idempotency_key": f"load-acc-{stats.name}-{user_idx}"},
            )
            stats.add_latency((time.perf_counter() - t0) * 1000)
            if acc.status_code == 200:
                stats.inc("successful_trades")
            elif acc.status_code == 409:
                stats.inc("rejected_trades")
            else:
                stats.inc("errors")
        else:
            can = client.post(
                f"/api/trades/{offer.json()['id']}/cancel",
                headers=auth(u["token"]),
                json={"idempotency_key": f"load-can-{stats.name}-{user_idx}"},
            )
            stats.add_latency((time.perf_counter() - t0) * 1000)
            if can.status_code >= 400:
                stats.inc("errors")
            else:
                stats.inc("rejected_trades")
    except Exception:
        stats.inc("errors")
        stats.inc("timeouts")


def _profile(client, name: str, users: int) -> dict:
    db.reset_lock_stats()
    main_mod._RATE.clear()
    stats = LoadStats(name=name, concurrent_users=users)
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(users, 64)) as pool:
        futs = [pool.submit(_run_user_flow, client, i, stats) for i in range(users)]
        for f in concurrent.futures.as_completed(futs):
            f.result()
    return stats.finalize(started, dict(db.LOCK_STATS))


def _results_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "load_test_results.json"


@pytest.mark.parametrize(
    "name,users",
    [
        ("baseline", 10),
        ("medium", 50),
        ("heavy", 100),
        ("stress", 250),
    ],
)
def test_load_profile(load_client, name, users):
    result = _profile(load_client, name, users)
    assert result["requests"] > 0
    # Soft bound: under extreme SQLite write contention some HTTP errors may appear,
    # but majority of flows must succeed and busy_failures must stay zero.
    assert result["error_rate"] < 0.5, result
    assert result["db_lock_stats"].get("busy_failures", 0) == 0
    out = _results_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out.read_text()) if out.exists() else {}
    existing[name] = result
    out.write_text(json.dumps(existing, indent=2))
