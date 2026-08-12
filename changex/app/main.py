from __future__ import annotations

import sqlite3
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
from .metrics import compute_trade_metrics
from .moderation import (
    ModerationError,
    apply_superadmin_decision,
    remoderate_after_edit,
    run_ai_premoderation,
    user_status_message,
)
from .observability import safe_log_fields
from .recovery import recover_stale_reservations
from .states import (
    ListingStatus,
    ModerationDecision,
    PUBLIC_LISTING,
    TradeState,
    UserRole,
    InvalidTransition,
    normalize_listing_status,
    transition,
)
from .value import ChangeValue, ChangeValueError

WEB_DIR = Path(__file__).resolve().parents[2] / "changex_app" / "build" / "web"
ALT_WEB = Path("/home/ubuntu/varmisin-app/build/web")

# Structured request log sink (tests can replace). No secrets.
REQUEST_LOGS: list[dict[str, Any]] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="CHANGE X", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate buckets: key -> timestamps. Keys include ip / user / endpoint dimensions.
_RATE: dict[str, list[float]] = {}


def _rate_hit(key: str, limit: int, window: float) -> None:
    now = time.time()
    bucket = [t for t in _RATE.get(key, []) if now - t < window]
    if len(bucket) >= limit:
        raise HTTPException(
            429,
            detail={
                "code": "RATE_LIMIT",
                "message": "Çok fazla istek",
                "scope": key.split(":")[0],
                "key": key,
            },
        )
    bucket.append(now)
    _RATE[key] = bucket


def _rate_limit(
    request: Request,
    limit: int = 60,
    window: float = 60.0,
    *,
    endpoint: str | None = None,
    user_id: int | None = None,
    global_ip_limit: int = 600,
) -> None:
    """Enforce IP + endpoint (+ optional user) rate limits independently."""
    ip = request.client.host if request.client else "unknown"
    ep = endpoint or request.url.path
    _rate_hit(f"ip:{ip}", global_ip_limit, window)
    _rate_hit(f"ip:{ip}:ep:{ep}", limit, window)
    if user_id is not None:
        _rate_hit(f"user:{user_id}", global_ip_limit, window)
        _rate_hit(f"user:{user_id}:ep:{ep}", limit, window)


def _cid(request: Request) -> str:
    return request.headers.get("x-correlation-id") or str(uuid.uuid4())


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    request.state.correlation_id = cid
    start = time.perf_counter()
    error_code = None
    result = "ok"
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            result = "error"
            error_code = str(response.status_code)
        response.headers["X-Correlation-Id"] = cid
        return response
    except Exception:
        result = "error"
        error_code = "UNHANDLED"
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        entry = safe_log_fields(
            actor_id=getattr(request.state, "actor_id", None),
            action=f"{request.method} {request.url.path}",
            entity="request",
            result=result,
            error_code=error_code,
            duration_ms=round(duration_ms, 3),
            correlation_id=cid,
        )
        # Never log Authorization / password / token bodies
        REQUEST_LOGS.append(entry)
        if len(REQUEST_LOGS) > 5000:
            del REQUEST_LOGS[:2500]


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
    category: str | None = None
    photo_urls: list[str] | None = None
    # Ignored / rejected if present — users cannot self-approve
    status: str | None = None


class ModerationDecisionIn(BaseModel):
    decision: ModerationDecision
    reason: str = ""


class OfferCreateIn(BaseModel):
    """Multi-listing offer. Server recalculates values from listing mandal_units."""

    requested_listing_ids: list[int] = Field(min_length=1)
    offered_listing_ids: list[int] = Field(min_length=1)
    idempotency_key: str | None = None
    expires_in_seconds: int = Field(default=86_400, ge=60, le=7 * 86_400)
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
    _rate_limit(request, limit=180, endpoint=request.url.path)
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
        user = db.row_to_dict(row)
        if user:
            if int(user.get("suspended") or 0) == 1:
                raise HTTPException(
                    403,
                    detail={"code": "USER_SUSPENDED", "message": "Hesap askıda"},
                )
            request.state.actor_id = user["id"]
            _rate_limit(
                request,
                limit=120,
                endpoint=request.url.path,
                user_id=int(user["id"]),
            )
        return user


def require_user(user: Annotated[dict | None, Depends(current_user)]) -> dict:
    if not user:
        raise HTTPException(401, detail={"code": "AUTH_REQUIRED", "message": "Giriş gerekli"})
    return user


def require_admin(user: Annotated[dict, Depends(require_user)]) -> dict:
    if user.get("role") not in {UserRole.ADMIN.value, UserRole.SUPERADMIN.value}:
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED", "message": "Admin yetkisi gerekli"})
    return user


def require_superadmin(user: Annotated[dict, Depends(require_user)]) -> dict:
    if user.get("role") != UserRole.SUPERADMIN.value:
        raise HTTPException(
            403,
            detail={"code": "SUPERADMIN_REQUIRED", "message": "Superadmin yetkisi gerekli"},
        )
    return user


def _http_domain(exc: DomainError) -> HTTPException:
    return HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.message})


def _http_mod(exc: ModerationError) -> HTTPException:
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
        "version": "0.3.0",
        "core": "trust_safety_v1",
    }


@app.post("/api/auth/register")
def register(body: RegisterIn, request: Request) -> dict:
    _rate_limit(request, limit=15, endpoint="/api/auth/register")
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
        request.state.actor_id = uid
        db.audit(conn, actor_id=uid, action="register", entity="user", entity_id=uid, detail=username, correlation_id=_cid(request))
        return {"token": token, "user": {"id": uid, "username": username, "role": "user"}}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request) -> dict:
    _rate_limit(request, limit=20, endpoint="/api/auth/login")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (body.username.strip(),),
        ).fetchone()
        if not row or not db.verify_password(body.password, row["password_hash"]):
            raise HTTPException(401, detail={"code": "BAD_CREDENTIALS", "message": "Kullanıcı veya şifre hatalı"})
        token = _new_session(conn, row["id"])
        request.state.actor_id = row["id"]
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
    # Public feed: APPROVED only (ACTIVE legacy treated as approved via SQL IN)
    sql = "SELECT * FROM trade_listings WHERE status IN ('APPROVED', 'ACTIVE')"
    args: list[Any] = []
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


@app.get("/api/listings/mine")
def my_listings(user: Annotated[dict, Depends(require_user)]) -> dict:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM trade_listings WHERE owner_id = ? ORDER BY updated_at DESC LIMIT 100",
            (user["id"],),
        ).fetchall()
        return {"listings": [_listing_public(conn, dict(r), include_moderation=True) for r in rows]}


@app.get("/api/listings/{listing_id}")
def get_listing(
    listing_id: int,
    user: Annotated[dict | None, Depends(current_user)] = None,
) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND", "message": "Takas kaydı bulunamadı"})
        d = dict(row)
        status = normalize_listing_status(d["status"])
        is_owner = user and int(user["id"]) == int(d["owner_id"])
        is_staff = user and user.get("role") in {
            UserRole.ADMIN.value,
            UserRole.SUPERADMIN.value,
        }
        # Marketplace-visible lifecycle (post-approval) may be fetched by id.
        # Pre-approval / rejected stay private except owner/staff.
        visible_by_id = PUBLIC_LISTING | {
            ListingStatus.RESERVED,
            ListingStatus.TRADED,
            ListingStatus.CANCELLED,
            ListingStatus.EXPIRED,
        }
        if status not in visible_by_id and not is_owner and not is_staff:
            raise HTTPException(
                404,
                detail={"code": "LISTING_NOT_FOUND", "message": "Takas kaydı bulunamadı"},
            )
        return _listing_public(conn, d, include_moderation=bool(is_owner or is_staff))


@app.post("/api/listings")
def create_listing(
    body: ListingCreateIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    _rate_limit(request, limit=40, endpoint="/api/listings", user_id=int(user["id"]))
    # Bypass attempts via unexpected status field are ignored (not in model for create)
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
    cid = _cid(request)
    with db.connect() as conn:
        with db.immediate_tx(conn):
            cur = conn.execute(
                """
                INSERT INTO trade_listings(
                  owner_id, title, description, category, subcategory, condition,
                  location, mandal_units, accept_categories, wanted_items,
                  min_mandal_units, max_mandal_units, photo_urls, status, version,
                  moderation_version, created_at, updated_at, moderation_updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    ListingStatus.PENDING_MODERATION.value,
                    1,
                    1,
                    now,
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
                correlation_id=cid,
            )
            run_ai_premoderation(conn, listing_id=lid, correlation_id=cid)
            row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (lid,)).fetchone()
            out = _listing_public(conn, dict(row), include_moderation=True)
            out["user_message"] = user_status_message(out["status"])
            return out


@app.patch("/api/listings/{listing_id}")
def update_listing(
    listing_id: int,
    body: ListingUpdateIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    if body.status is not None:
        raise HTTPException(
            403,
            detail={
                "code": "STATUS_IMMUTABLE",
                "message": "Listing durumu kullanıcı tarafından değiştirilemez",
            },
        )
    cid = _cid(request)
    with db.connect() as conn:
        with db.immediate_tx(conn):
            row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
            if not row:
                raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND", "message": "Bulunamadı"})
            if int(row["owner_id"]) != user["id"] and user.get("role") not in {
                UserRole.ADMIN.value,
                UserRole.SUPERADMIN.value,
            }:
                raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Bu kaydı değiştiremezsin"})
            status = normalize_listing_status(row["status"])
            if status in {
                ListingStatus.RESERVED,
                ListingStatus.TRADED,
                ListingStatus.CANCELLED,
            }:
                raise HTTPException(409, detail={"code": "NOT_EDITABLE", "message": "Bu durumda düzenlenemez"})

            title = body.title.strip() if body.title is not None else row["title"]
            description = body.description if body.description is not None else row["description"]
            wanted = body.wanted_items if body.wanted_items is not None else row["wanted_items"]
            location = body.location if body.location is not None else row["location"]
            category = body.category.strip() if body.category is not None else row["category"]
            photos = body.photo_urls if body.photo_urls is not None else db.loads(row["photo_urls"], [])

            critical = False
            if body.title is not None and title != row["title"]:
                critical = True
            if body.description is not None and description != row["description"]:
                critical = True
            if body.category is not None and category != row["category"]:
                critical = True
            if body.wanted_items is not None and wanted != row["wanted_items"]:
                critical = True
            if body.photo_urls is not None and photos != db.loads(row["photo_urls"], []):
                critical = True

            if critical:
                conn.execute(
                    """
                    UPDATE trade_listings
                    SET title=?, description=?, wanted_items=?, location=?, category=?,
                        photo_urls=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        title,
                        description,
                        wanted,
                        location,
                        category,
                        db.dumps(photos),
                        time.time(),
                        listing_id,
                    ),
                )
                remoderate_after_edit(
                    conn, listing_id=listing_id, actor_id=user["id"], correlation_id=cid
                )
            else:
                # Safe metadata (location only) without remotion
                conn.execute(
                    """
                    UPDATE trade_listings
                    SET title=?, description=?, wanted_items=?, location=?, category=?,
                        photo_urls=?, updated_at=?, version=version+1
                    WHERE id=? AND version=?
                    """,
                    (
                        title,
                        description,
                        wanted,
                        location,
                        category,
                        db.dumps(photos),
                        time.time(),
                        listing_id,
                        row["version"],
                    ),
                )
                db.audit(
                    conn,
                    actor_id=user["id"],
                    action="listing.update",
                    entity="listing",
                    entity_id=listing_id,
                    correlation_id=cid,
                )
            row2 = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
            out = _listing_public(conn, dict(row2), include_moderation=True)
            out["user_message"] = user_status_message(out["status"])
            return out


@app.post("/api/trades/offer")
def create_offer_api(
    body: OfferCreateIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    _rate_limit(request, limit=40, endpoint="/api/trades/offer", user_id=int(user["id"]))
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
    _rate_limit(request, limit=40, endpoint="/api/trades/accept", user_id=int(user["id"]))
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
    _rate_limit(request, limit=40, endpoint="/api/trades/cancel", user_id=int(user["id"]))
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
        pending = conn.execute(
            """
            SELECT COUNT(*) c FROM trade_listings
            WHERE status IN ('PENDING_MODERATION','AI_REVIEW','ADMIN_REVIEW','MODERATION_UNAVAILABLE')
            """
        ).fetchone()["c"]
        return {
            "users": users,
            "listings": listings,
            "trades": trades,
            "moderation_queue": pending,
            "real_money": False,
        }


@app.get("/api/admin/moderation/queue")
def moderation_queue(user: Annotated[dict, Depends(require_superadmin)]) -> dict:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM trade_listings
            WHERE status IN ('PENDING_MODERATION','AI_REVIEW','ADMIN_REVIEW','MODERATION_UNAVAILABLE','EDIT_REQUIRED')
            ORDER BY moderation_priority DESC, created_at ASC
            LIMIT 200
            """
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            owner = conn.execute(
                "SELECT id, username, user_risk_score, change_score, role FROM users WHERE id = ?",
                (d["owner_id"],),
            ).fetchone()
            decisions = conn.execute(
                """
                SELECT * FROM moderation_decisions
                WHERE listing_id = ? ORDER BY created_at DESC LIMIT 10
                """,
                (d["id"],),
            ).fetchall()
            photos = conn.execute(
                "SELECT * FROM listing_photos WHERE listing_id = ? ORDER BY id DESC LIMIT 20",
                (d["id"],),
            ).fetchall()
            pub = _listing_public(conn, d, include_moderation=True)
            pub["owner_history"] = {
                "user_risk_score": (owner["user_risk_score"] if owner else 0),
                "change_score": (owner["change_score"] if owner else 0),
            }
            pub["prior_decisions"] = [dict(x) for x in decisions]
            pub["photo_moderation"] = [dict(x) for x in photos]
            items.append(pub)
        return {"queue": items, "count": len(items)}


@app.post("/api/admin/moderation/{listing_id}/decision")
def moderation_decision_api(
    listing_id: int,
    body: ModerationDecisionIn,
    request: Request,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict:
    with db.connect() as conn:
        try:
            with db.immediate_tx(conn):
                row = apply_superadmin_decision(
                    conn,
                    listing_id=listing_id,
                    actor_id=int(user["id"]),
                    actor_role=user["role"],
                    decision=body.decision,
                    reason=body.reason,
                    correlation_id=_cid(request),
                )
            return _listing_public(conn, row, include_moderation=True)
        except ModerationError as exc:
            raise _http_mod(exc) from exc


@app.get("/api/admin/moderation/{listing_id}/audit")
def moderation_audit(
    listing_id: int,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict:
    with db.connect() as conn:
        decisions = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM moderation_decisions WHERE listing_id = ? ORDER BY created_at DESC",
                (listing_id,),
            ).fetchall()
        ]
        audits = [
            dict(r)
            for r in conn.execute(
                """
                SELECT * FROM audit_logs
                WHERE entity = 'listing' AND entity_id = ?
                ORDER BY created_at DESC LIMIT 50
                """,
                (listing_id,),
            ).fetchall()
        ]
        return {"decisions": decisions, "audit_logs": audits}


@app.post("/api/admin/moderation/{listing_id}/rerun-ai")
def moderation_rerun_ai(
    listing_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict:
    with db.connect() as conn:
        with db.immediate_tx(conn):
            conn.execute(
                "UPDATE trade_listings SET status = ? WHERE id = ?",
                (ListingStatus.PENDING_MODERATION.value, listing_id),
            )
            result = run_ai_premoderation(
                conn, listing_id=listing_id, correlation_id=_cid(request)
            )
        return result



@app.get("/api/admin/metrics")
def admin_metrics(user: Annotated[dict, Depends(require_admin)]) -> dict:
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM trades").fetchall()]
        domain = compute_trade_metrics(rows)
        return {
            "domain": domain,
            "sqlite_lock_stats": dict(db.LOCK_STATS),
            "real_money": False,
            "asset_lock_note": "Future multi-party trades use ASSET LOCK, not money escrow",
        }


@app.post("/api/admin/recover")
def admin_recover(user: Annotated[dict, Depends(require_admin)]) -> dict:
    with db.connect() as conn:
        with db.immediate_tx(conn):
            result = recover_stale_reservations(conn, older_than_seconds=0)
        return result


@app.get("/api/observability/sample")
def observability_sample(user: Annotated[dict, Depends(require_admin)]) -> dict:
    """Return recent safe log fields (no tokens/passwords)."""
    sample = REQUEST_LOGS[-20:]
    blob = str(sample).lower()
    assert "password" not in blob
    return {"entries": sample, "count": len(REQUEST_LOGS)}


def _listing_public(conn, row: dict, include_moderation: bool = False) -> dict:
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
    status = str(row.get("status") or "PENDING_MODERATION").upper()
    if status == "ACTIVE":
        status = "APPROVED"
    all_photos = db.loads(row.get("photo_urls") or "[]", [])
    # Public viewers only see photos approved for current moderation_version
    public_photos: list[str] = []
    try:
        approved_rows = conn.execute(
            """
            SELECT url FROM listing_photos
            WHERE listing_id = ? AND moderation_status = 'APPROVED'
              AND moderation_version = ?
            """,
            (row["id"], int(row.get("moderation_version") or 1)),
        ).fetchall()
        public_photos = [r["url"] for r in approved_rows]
    except sqlite3.Error:
        public_photos = []
    if status in {"APPROVED"} and not public_photos and include_moderation:
        public_photos = all_photos
    elif status in {"APPROVED"} and not public_photos:
        # Legacy listings without photo moderation rows: show stored urls only when approved
        public_photos = all_photos

    out = {
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
        "photo_urls": public_photos if not include_moderation else all_photos,
        "items": item_out,
        "status": status,
        "version": row.get("version", 1),
        "moderation_version": row.get("moderation_version", 1),
        "owner": {
            "id": row["owner_id"],
            "username": owner["username"] if owner else "?",
            "change_score": owner["change_score"] if owner else 0,
        },
        "owner_id": row["owner_id"],
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
        "user_message": user_status_message(status),
    }
    if include_moderation:
        out.update(
            {
                "ai_result": row.get("ai_result"),
                "ai_confidence": row.get("ai_confidence"),
                "ai_categories": db.loads(row.get("ai_categories") or "[]", []),
                "ai_policy_version": row.get("ai_policy_version"),
                "risk_level": row.get("risk_level"),
                "moderation_priority": row.get("moderation_priority"),
                "moderation_reason": row.get("moderation_reason"),
                "approved_at": row.get("approved_at"),
                "approved_by": row.get("approved_by"),
                "all_photo_urls": all_photos,
            }
        )
    return out


# Change Chain gate stub — unapproved listings must never enter matching
@app.post("/api/change-chain/match")
def change_chain_match_stub(
    body: OfferCreateIn,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db.connect() as conn:
        for lid in list(body.requested_listing_ids) + list(body.offered_listing_ids):
            row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (lid,)).fetchone()
            if not row:
                raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND", "message": "Listing yok"})
            if normalize_listing_status(row["status"]) not in PUBLIC_LISTING:
                raise HTTPException(
                    409,
                    detail={
                        "code": "LISTING_NOT_APPROVED",
                        "message": "Onaysız listing Change Chain'e giremez",
                    },
                )
    raise HTTPException(
        501,
        detail={"code": "CHANGE_CHAIN_NOT_IMPLEMENTED", "message": "Change Chain henüz yok"},
    )



def _web_root() -> Path | None:
    if (ALT_WEB / "index.html").exists():
        return ALT_WEB
    if (WEB_DIR / "index.html").exists():
        return WEB_DIR
    return None


_static = _web_root()
if _static is not None:
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="web")
