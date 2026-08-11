"""Rate-limited HTTP client for official Paribu REST (api.paribu.com)."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_API_BASE = "https://api.paribu.com"
USER_AGENT = "KocaKafa-Crypto/2.0 (+market-data; no-trading)"


class ParibuHTTPError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class ParibuRateLimitError(ParibuHTTPError):
    def __init__(self, retry_after: float, body: str = "") -> None:
        super().__init__(f"rate_limit retry_after={retry_after}", status=429, body=body)
        self.retry_after = retry_after


@dataclass
class HTTPResponse:
    status: int
    headers: dict[str, str]
    data: Any
    fetched_at: float


class ParibuHTTPClient:
    """Shared GET client with min-interval + 429 backoff. Dedupes in-flight identical URLs."""

    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        *,
        min_interval_sec: float = 0.25,
        timeout_sec: float = 15.0,
        opener: Any | None = None,
    ) -> None:
        self.api_base = (api_base or DEFAULT_API_BASE).rstrip("/")
        self.min_interval_sec = max(0.05, float(min_interval_sec))
        self.timeout_sec = timeout_sec
        self._lock = threading.Lock()
        self._last_request_at = 0.0
        self._inflight: dict[str, threading.Event] = {}
        self._cache: dict[str, HTTPResponse] = {}
        self._opener = opener  # injectable for tests

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        cache_ttl_sec: float = 0.0,
        weight: int = 1,
    ) -> HTTPResponse:
        del weight  # documented for callers; bucket enforced via min_interval + 429
        url = self._url(path, params)
        now = time.time()
        with self._lock:
            cached = self._cache.get(url)
            if cached and cache_ttl_sec > 0 and (now - cached.fetched_at) <= cache_ttl_sec:
                return cached

        self._throttle()
        try:
            raw_status, headers, body = self._do_get(url)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace") if exc.fp else ""
            if exc.code == 429:
                retry = self._parse_retry_after(exc.headers, body)
                raise ParibuRateLimitError(retry, body) from exc
            raise ParibuHTTPError(f"HTTP {exc.code} {path}", status=exc.code, body=body) from exc
        except urllib.error.URLError as exc:
            raise ParibuHTTPError(f"network error: {exc.reason}", status=None) from exc

        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError as exc:
            raise ParibuHTTPError("invalid JSON", status=raw_status, body=body[:500]) from exc

        resp = HTTPResponse(status=raw_status, headers=headers, data=data, fetched_at=time.time())
        with self._lock:
            self._cache[url] = resp
        return resp

    def _url(self, path: str, params: dict[str, Any] | None) -> str:
        p = path if path.startswith("/") else f"/{path}"
        url = f"{self.api_base}{p}"
        if params:
            q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{q}"
        return url

    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_interval_sec - (time.time() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        with self._lock:
            self._last_request_at = time.time()

    def _do_get(self, url: str) -> tuple[int, dict[str, str], str]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            method="GET",
        )
        if self._opener is not None:
            with self._opener.open(req, timeout=self.timeout_sec) as r:
                return int(r.status), {k: v for k, v in r.headers.items()}, r.read().decode("utf-8", "replace")
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as r:
            return int(r.status), {k: v for k, v in r.headers.items()}, r.read().decode("utf-8", "replace")

    @staticmethod
    def _parse_retry_after(headers: Any, body: str) -> float:
        try:
            if headers and headers.get("Retry-After"):
                return float(headers.get("Retry-After"))
        except (TypeError, ValueError):
            pass
        try:
            payload = json.loads(body or "{}")
            return float(payload.get("retry_after") or 1)
        except (TypeError, ValueError, json.JSONDecodeError):
            return 1.0
