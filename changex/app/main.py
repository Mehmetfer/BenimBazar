from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import db
from .engine import (
    DomainError,
    accept_offer,
    cancel_offer,
    complete_trade,
    confirm_trade,
    create_offer,
    trade_public,
)
from .states import ListingStatus, TradeState, InvalidTransition, transition
from .value import ChangeValue, ChangeValueError, value_gap

WEB_DIR = Path(__file__).resolve().parents[2] / "changex_app" / "build" / "web"
ALT_WEB = Path("/home/ubuntu/varmisin-app/build/web")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="CHANGE X", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RATE: dict[str, list[float]] = {}


def _rate_limit(request: Request, limit: int = 60, window: float = 60.0) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = [t for t in _RATE.get(ip, []) if now - t < window]
    if len(bucket) >= limit:
        raise HTTPException(429, detail={"code": "RATE_LIMIT", "message": "Çok fazla istek"})
    bucket.append(now)
    _RATE[ip] = bucket


def _cid(request: Request) -> str:
    return request.headers.get("x-correlation-id") or str(uuid.uuid4())


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=4, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class ValueIn(BaseModel):
    madalyon: int = 0
    dirhem: int = 0
    mandal: int = 0

    @field_validator("madalyon", "dirhem", "mandal", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("floating-point değer kabul edilmez")
        if isinstance(v, bool):
            raise ValueError("geçersiz değer")
        return v


class ListingItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: ValueIn


class ListingCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = ""
    category: str = Field(min_length=1, max_length=80)
    subcategory: str = ""
    condition: str = "good"
    location: str = ""
    items: list[ListingItemIn] = Field(min_length=1)
    accept_categories: list[str] = []
    wanted_items: str = ""
    min_value: ValueIn | None = None
    max_value: ValueIn | None = None
    photo_urls: list[str] = []


class ListingUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    wanted_items: str | None = None
    location: str | None = None


class OfferCreateIn(BaseModel):
    """Multi-listing offer. Server recalculates values from listing mandal_units."""

    requested_listing_ids: list[int] = Field(min_length=1)
    offered_listing_ids: list[int] = Field(min_length=1)
    idempotency_key: str | None = None
    expires_in_seconds: int = Field(default=86_400, ge=60, le=7 * 86_400)

    # Legacy single-listing helper (optional)
    listing_id: int | None = None


class TransitionIn(BaseModel):
    target_state: TradeState
    note: str = ""
    idempotency_key: str | None = None


class IdempotentActionIn(BaseModel):
    idempotency_key: str | None = None
    note: str = ""


def current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any] | None:
    _rate_limit(request, limit=120)
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, time.time()),
        ).fetchone()
        return db.row_to_dict(row)


def require_user(user: Annotated[dict | None, Depends(current_user)]) -> dict:
    if not user:
        raise HTTPException(401, detail={"code": "AUTH_REQUIRED", "message": "Giriş gerekli"})
    return user


def require_admin(user: Annotated[dict, Depends(require_user)]) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED", "message": "Admin yetkisi gerekli"})
    return user


def _http_domain(exc: DomainError) -> HTTPException:
    return HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.message})


def _parse_value(body: ValueIn) -> ChangeValue:
    try:
        return ChangeValue.from_units(
            madalyon=body.madalyon, dirhem=body.dirhem, mandal=body.mandal
        )
    except ChangeValueError as exc:
        raise HTTPException(
            400, detail={"code": "INVALID_VALUE", "message": str(exc)}
        ) from exc


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": "CHANGE X",
        "real_money": False,
        "unit_system": "CHANGE_X",
        "units": ["Mandal", "Dirhem", "Madalyon"],
        "canonical": "mandal_units",
        "version": "0.2.0",
    }


@app.post("/api/auth/register")
def register(body: RegisterIn, request: Request) -> dict:
    _rate_limit(request, limit=20)
    username = body.username.strip()
    with db.connect() as conn:
        exists = conn.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if exists:
            raise HTTPException(409, detail={"code": "USERNAME_TAKEN", "message": "Bu kullanıcı adı alınmış"})
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES (?,?,?)",
            (username, db.hash_password(body.password), time.time()),
        )
        uid = int(cur.lastrowid)
        token = _new_session(conn, uid)
        db.audit(conn, actor_id=uid, action="register", entity="user", entity_id=uid, detail=username, correlation_id=_cid(request))
        return {"token": token, "user": {"id": uid, "username": username, "role": "user"}}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request) -> dict:
    _rate_limit(request, limit=30)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (body.username.strip(),),
        ).fetchone()
        if not row or not db.verify_password(body.password, row["password_hash"]):
            raise HTTPException(401, detail={"code": "BAD_CREDENTIALS", "message": "Kullanıcı veya şifre hatalı"})
        token = _new_session(conn, row["id"])
        db.audit(conn, actor_id=row["id"], action="login", entity="user", entity_id=row["id"], correlation_id=_cid(request))
        return {
            "token": token,
            "user": {
                "id": row["id"],
                "username": row["username"],
                "role": row["role"],
                "change_score": row["change_score"],
            },
        }


def _new_session(conn, user_id: int) -> str:
    import secrets

    token = secrets.token_urlsafe(32)
    now = time.time()
    conn.execute(
        "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, now, now + 60 * 60 * 24 * 30),
    )
    return token


@app.get("/api/auth/me")
def me(user: Annotated[dict | None, Depends(current_user)]) -> dict:
    if not user:
        raise HTTPException(401, detail={"code": "AUTH_REQUIRED", "message": "Giriş gerekli"})
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "change_score": user["change_score"],
    }


@app.post("/api/value/normalize")
def normalize_value(body: ValueIn) -> dict:
    return _parse_value(body).serialize()


@app.get("/api/listings")
def list_listings(
    q: str | None = None,
    category: str | None = None,
    user: Annotated[dict | None, Depends(current_user)] = None,
) -> dict:
    sql = "SELECT * FROM trade_listings WHERE status = ?"
    args: list[Any] = [ListingStatus.ACTIVE.value]
    if category and category not in {"Lobi", "TÜM TAKASLAR", "Tumu", "Tümü"}:
        sql += " AND category = ?"
        args.append(category)
    if q:
        sql += " AND (title LIKE ? OR description LIKE ? OR wanted_items LIKE ?)"
        like = f"%{q}%"
        args.extend([like, like, like])
    sql += " ORDER BY created_at DESC LIMIT 100"
    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
        items = [_listing_public(conn, dict(r)) for r in rows]
    return {"listings": items, "viewer": user["username"] if user else None}


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND", "message": "Takas kaydı bulunamadı"})
        return _listing_public(conn, dict(row))


@app.post("/api/listings")
def create_listing(
    body: ListingCreateIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    try:
        item_vals = [
            (it.name, _parse_value(it.value)) for it in body.items
        ]
    except HTTPException:
        raise
    total = ChangeValue.zero()
    for _, v in item_vals:
        total = total.add(v)
    if total.mandal_units <= 0:
        raise HTTPException(400, detail={"code": "ZERO_VALUE", "message": "Takas değeri sıfır olamaz"})
    min_v = _parse_value(body.min_value) if body.min_value else ChangeValue.zero()
    max_v = _parse_value(body.max_value) if body.max_value else total
    now = time.time()
    with db.connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO trade_listings(
              owner_id, title, description, category, subcategory, condition,
              location, mandal_units, accept_categories, wanted_items,
              min_mandal_units, max_mandal_units, photo_urls, status, version,
              created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user["id"],
                body.title.strip(),
                body.description.strip(),
                body.category.strip(),
                body.subcategory.strip(),
                body.condition,
                body.location.strip(),
                total.mandal_units,
                db.dumps(body.accept_categories),
                body.wanted_items.strip(),
                min_v.mandal_units,
                max_v.mandal_units,
                db.dumps(body.photo_urls),
                ListingStatus.ACTIVE.value,
                1,
                now,
                now,
            ),
        )
        lid = int(cur.lastrowid)
        for name, val in item_vals:
            conn.execute(
                "INSERT INTO listing_items(listing_id, name, mandal_units) VALUES (?,?,?)",
                (lid, name, val.mandal_units),
            )
        db.audit(
            conn,
            actor_id=user["id"],
            action="listing.create",
            entity="listing",
            entity_id=lid,
            correlation_id=_cid(request),
        )
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (lid,)).fetchone()
        return _listing_public(conn, dict(row))


@app.patch("/api/listings/{listing_id}")
def update_listing(
    listing_id: int,
    body: ListingUpdateIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND", "message": "Bulunamadı"})
        if int(row["owner_id"]) != user["id"] and user.get("role") != "admin":
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Bu kaydı değiştiremezsin"})
        if str(row["status"]).upper() != ListingStatus.ACTIVE.value:
            raise HTTPException(409, detail={"code": "NOT_ACTIVE", "message": "Yalnız ACTIVE kayıt güncellenir"})
        title = body.title.strip() if body.title is not None else row["title"]
        description = body.description if body.description is not None else row["description"]
        wanted = body.wanted_items if body.wanted_items is not None else row["wanted_items"]
        location = body.location if body.location is not None else row["location"]
        conn.execute(
            """
            UPDATE trade_listings
            SET title=?, description=?, wanted_items=?, location=?, updated_at=?, version=version+1
            WHERE id=? AND version=?
            """,
            (title, description, wanted, location, time.time(), listing_id, row["version"]),
        )
        db.audit(
            conn,
            actor_id=user["id"],
            action="listing.update",
            entity="listing",
            entity_id=listing_id,
            correlation_id=_cid(request),
        )
        row2 = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
        return _listing_public(conn, dict(row2))


@app.post("/api/trades/offer")
def create_offer_api(
    body: OfferCreateIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    requested = list(body.requested_listing_ids)
    if body.listing_id is not None and body.listing_id not in requested:
        requested = [body.listing_id, *requested]
    with db.connect() as conn:
        try:
            return create_offer(
                conn,
                proposer_id=user["id"],
                requested_listing_ids=requested,
                offered_listing_ids=body.offered_listing_ids,
                idempotency_key=body.idempotency_key,
                expires_in_seconds=body.expires_in_seconds,
                correlation_id=_cid(request),
            )
        except DomainError as exc:
            raise _http_domain(exc) from exc
        except ChangeValueError as exc:
            raise HTTPException(400, detail={"code": "INVALID_VALUE", "message": str(exc)}) from exc


@app.post("/api/trades/{trade_id}/accept")
def accept_offer_api(
    trade_id: int,
    body: IdempotentActionIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db.connect() as conn:
        try:
            return accept_offer(
                conn,
                trade_id=trade_id,
                actor_id=user["id"],
                idempotency_key=body.idempotency_key,
                correlation_id=_cid(request),
            )
        except DomainError as exc:
            raise _http_domain(exc) from exc


@app.post("/api/trades/{trade_id}/cancel")
def cancel_offer_api(
    trade_id: int,
    body: IdempotentActionIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db.connect() as conn:
        try:
            return cancel_offer(
                conn,
                trade_id=trade_id,
                actor_id=user["id"],
                idempotency_key=body.idempotency_key,
                correlation_id=_cid(request),
            )
        except DomainError as exc:
            raise _http_domain(exc) from exc


@app.post("/api/trades/{trade_id}/confirm")
def confirm_trade_api(
    trade_id: int,
    body: IdempotentActionIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db.connect() as conn:
        try:
            return confirm_trade(
                conn,
                trade_id=trade_id,
                actor_id=user["id"],
                idempotency_key=body.idempotency_key,
                correlation_id=_cid(request),
            )
        except DomainError as exc:
            raise _http_domain(exc) from exc


@app.post("/api/trades/{trade_id}/complete")
def complete_trade_api(
    trade_id: int,
    body: IdempotentActionIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db.connect() as conn:
        try:
            return complete_trade(
                conn,
                trade_id=trade_id,
                actor_id=user["id"],
                idempotency_key=body.idempotency_key,
                correlation_id=_cid(request),
            )
        except DomainError as exc:
            raise _http_domain(exc) from exc


@app.post("/api/trades/{trade_id}/transition")
def trade_transition(
    trade_id: int,
    body: TransitionIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    """Generic transition — prefer dedicated accept/cancel/confirm/complete endpoints."""
    if body.target_state == TradeState.ACCEPTED:
        return accept_offer_api(trade_id, IdempotentActionIn(idempotency_key=body.idempotency_key, note=body.note), request, user)
    if body.target_state == TradeState.CANCELLED:
        return cancel_offer_api(trade_id, IdempotentActionIn(idempotency_key=body.idempotency_key, note=body.note), request, user)
    if body.target_state == TradeState.CONFIRMED:
        return confirm_trade_api(trade_id, IdempotentActionIn(idempotency_key=body.idempotency_key, note=body.note), request, user)
    if body.target_state == TradeState.COMPLETED:
        return complete_trade_api(trade_id, IdempotentActionIn(idempotency_key=body.idempotency_key, note=body.note), request, user)

    with db.connect() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise HTTPException(404, detail={"code": "TRADE_NOT_FOUND", "message": "Takas bulunamadı"})
        t = dict(trade)
        if user["id"] not in (t.get("proposer_id") or t.get("initiator_id"), t.get("receiver_id") or t.get("counterparty_id")) and user.get("role") != "admin":
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Bu takasa erişimin yok"})
        current = TradeState(t.get("status") or t.get("state"))
        try:
            new_state = transition(current, body.target_state)
        except InvalidTransition as exc:
            raise HTTPException(400, detail={"code": "INVALID_STATE", "message": str(exc)}) from exc
        now = time.time()
        conn.execute(
            "UPDATE trades SET status = ?, updated_at = ?, version = version + 1 WHERE id = ?",
            (new_state.value, now, trade_id),
        )
        conn.execute(
            """
            INSERT INTO trade_events(trade_id, actor_id, from_state, to_state, note, correlation_id, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (trade_id, user["id"], current.value, new_state.value, body.note, _cid(request), now),
        )
        db.audit(conn, actor_id=user["id"], action="trade.transition", entity="trade", entity_id=trade_id, detail=f"{current.value}->{new_state.value}", correlation_id=_cid(request))
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return trade_public(conn, dict(row))


@app.get("/api/trades/mine")
def my_trades(user: Annotated[dict, Depends(require_user)]) -> dict:
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
        if "proposer_id" in cols:
            rows = conn.execute(
                """
                SELECT * FROM trades
                WHERE proposer_id = ? OR receiver_id = ?
                ORDER BY updated_at DESC LIMIT 100
                """,
                (user["id"], user["id"]),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM trades
                WHERE initiator_id = ? OR counterparty_id = ?
                ORDER BY updated_at DESC LIMIT 100
                """,
                (user["id"], user["id"]),
            ).fetchall()
        return {"trades": [trade_public(conn, dict(r)) for r in rows]}


@app.get("/api/admin/stats")
def admin_stats(user: Annotated[dict, Depends(require_admin)]) -> dict:
    with db.connect() as conn:
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        listings = conn.execute("SELECT COUNT(*) c FROM trade_listings").fetchone()["c"]
        trades = conn.execute("SELECT COUNT(*) c FROM trades").fetchone()["c"]
        return {"users": users, "listings": listings, "trades": trades, "real_money": False}


def _listing_public(conn, row: dict) -> dict:
    item_cols = {r["name"] for r in conn.execute("PRAGMA table_info(listing_items)").fetchall()}
    if "mandal_units" in item_cols:
        items = conn.execute(
            "SELECT name, mandal_units FROM listing_items WHERE listing_id = ?",
            (row["id"],),
        ).fetchall()
        item_out = [
            {
                "name": i["name"],
                "value": ChangeValue.from_mandal_units(int(i["mandal_units"])).serialize(),
            }
            for i in items
        ]
    else:
        items = conn.execute(
            "SELECT name, value_mandal FROM listing_items WHERE listing_id = ?",
            (row["id"],),
        ).fetchall()
        item_out = [
            {
                "name": i["name"],
                "value": ChangeValue.from_mandal_units(int(i["value_mandal"])).serialize(),
            }
            for i in items
        ]
    owner = conn.execute(
        "SELECT username, change_score FROM users WHERE id = ?", (row["owner_id"],)
    ).fetchone()
    units = int(row["mandal_units"] if row.get("mandal_units") is not None else row.get("value_mandal") or 0)
    value = ChangeValue.from_mandal_units(units).serialize()
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "subcategory": row["subcategory"],
        "condition": row["condition"],
        "location": row["location"],
        "value": value,
        "mandal_units": units,
        "accept_categories": db.loads(row["accept_categories"] or "[]", []),
        "wanted_items": row["wanted_items"],
        "min_value": ChangeValue.from_mandal_units(
            int(row.get("min_mandal_units") or row.get("min_value_mandal") or 0)
        ).serialize(),
        "max_value": ChangeValue.from_mandal_units(
            int(row.get("max_mandal_units") or row.get("max_value_mandal") or 0)
        ).serialize(),
        "photo_urls": db.loads(row["photo_urls"] or "[]", []),
        "items": item_out,
        "status": str(row.get("status") or "ACTIVE").upper(),
        "version": row.get("version", 1),
        "owner": {
            "id": row["owner_id"],
            "username": owner["username"] if owner else "?",
            "change_score": owner["change_score"] if owner else 0,
        },
        "owner_id": row["owner_id"],
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
    }


def _web_root() -> Path | None:
    if (ALT_WEB / "index.html").exists():
        return ALT_WEB
    if (WEB_DIR / "index.html").exists():
        return WEB_DIR
    return None


_static = _web_root()
if _static is not None:
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="web")
