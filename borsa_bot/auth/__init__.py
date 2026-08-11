"""API authentication & authorization — fail-closed when AUTH_ENABLED.

Roles: VIEWER < TRADER < ADMIN
LIVE trading / kill switch / broker / risk settings require ADMIN (or TRADER where noted).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from config.settings import ROOT, settings
from fastapi import Header, HTTPException, Request


class Role(str, Enum):
    VIEWER = "VIEWER"
    TRADER = "TRADER"
    ADMIN = "ADMIN"


_ROLE_RANK = {Role.VIEWER: 1, Role.TRADER: 2, Role.ADMIN: 3}


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: Role
    token_hash: str


@dataclass
class AuthContext:
    username: str
    role: Role
    authenticated: bool


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "database" / "auth_users.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, tuple[str, Role, float]] = {}  # session -> (user, role, exp)
        self._ensure_bootstrap()

    def _ensure_bootstrap(self) -> None:
        if self.path.exists():
            return
        # Bootstrap from env — never write raw tokens into the file, only hashes
        users = []
        for env_key, role in (
            ("AUTH_ADMIN_TOKEN", Role.ADMIN),
            ("AUTH_TRADER_TOKEN", Role.TRADER),
            ("AUTH_VIEWER_TOKEN", Role.VIEWER),
        ):
            tok = os.getenv(env_key, "").strip()
            if tok:
                users.append(
                    {
                        "username": role.value.lower(),
                        "role": role.value,
                        "token_hash": _hash_token(tok),
                    }
                )
        # Dev default when auth enabled but no tokens: empty store (operator must set AUTH_*_TOKEN)
        self.path.write_text(json.dumps({"users": users, "note": "token_hash only — never store raw tokens"}, indent=2), encoding="utf-8")

    def users(self) -> list[AuthUser]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        out = []
        for u in data.get("users") or []:
            try:
                out.append(
                    AuthUser(
                        username=str(u["username"]),
                        role=Role(str(u["role"]).upper()),
                        token_hash=str(u["token_hash"]),
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return out

    def authenticate_token(self, token: str) -> AuthContext | None:
        if not token:
            return None
        digest = _hash_token(token)
        for u in self.users():
            if hmac.compare_digest(u.token_hash, digest):
                return AuthContext(u.username, u.role, True)
        # Session tokens
        sess = self._sessions.get(token)
        if sess:
            user, role, exp = sess
            if time.time() <= exp:
                return AuthContext(user, role, True)
            self._sessions.pop(token, None)
        return None

    def login(self, username: str, password_or_token: str) -> dict[str, Any]:
        ctx = self.authenticate_token(password_or_token)
        if ctx is None:
            # Also allow username match + token belonging to that user
            digest = _hash_token(password_or_token)
            for u in self.users():
                if u.username == username and hmac.compare_digest(u.token_hash, digest):
                    ctx = AuthContext(u.username, u.role, True)
                    break
        if ctx is None:
            raise HTTPException(401, "invalid credentials")
        session = secrets.token_urlsafe(32)
        ttl = int(getattr(settings, "auth_session_ttl_sec", 86400))
        self._sessions[session] = (ctx.username, ctx.role, time.time() + ttl)
        return {
            "ok": True,
            "session_token": session,
            "username": ctx.username,
            "role": ctx.role.value,
            "expires_in": ttl,
        }

    def require(self, authorization: str | None, *, min_role: Role) -> AuthContext:
        enabled = bool(getattr(settings, "auth_enabled", False))
        if not enabled:
            return AuthContext("anonymous", Role.ADMIN, False)  # open mode for local/dev
        if not authorization:
            raise HTTPException(401, "Authorization required")
        token = authorization
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
        ctx = self.authenticate_token(token)
        if ctx is None:
            raise HTTPException(401, "invalid token")
        if _ROLE_RANK[ctx.role] < _ROLE_RANK[min_role]:
            raise HTTPException(403, f"requires role {min_role.value}")
        return ctx


auth_store = AuthStore()


def require_role(min_role: Role) -> Callable:
    async def _dep(authorization: str | None = Header(default=None)) -> AuthContext:
        return auth_store.require(authorization, min_role=min_role)

    return _dep
