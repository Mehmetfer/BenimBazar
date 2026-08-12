from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
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
    apply_moderation_decision,
    apply_superadmin_decision,
    remoderate_after_edit,
    run_ai_premoderation,
    user_status_message,
)
from .matching import (
    CHANGE_CHAIN_ENABLED,
    WantValidationError,
    get_compatibility,
    get_user_preferences,
    is_chain_candidate,
    is_public_matchable,
    matchability_report,
    normalize_offer_fields,
    public_preferences_view,
    set_user_preferences,
    validate_structured_want,
)
from .matching import config as matching_config
from .matching.engine import ChainEngineError, run_chain_match
from .matching.proposals import (
    ChainProposalError,
    accept_proposal,
    list_proposals_for_user,
    proposal_public,
    reject_proposal,
)
from .matching.wants import validate_value_tolerance
from .domain_status import TradePreference
from .moderation.cache import cache_get, cache_set, invalidate_listing, reset_cache
from .observability import safe_log_fields
from .recovery import recover_stale_reservations
from .states import (
    ListingStatus,
    ModerationDecision,
    MODERATION_STAFF_ROLES,
    ASSIGNABLE_ROLES,
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
UPLOAD_DIR = db.DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

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
    location_city: str = ""
    location_district: str = ""
    location_country: str = ""
    brand: str = ""
    model_name: str = ""
    attributes: dict[str, Any] = {}
    items: list[ListingItemIn] = Field(min_length=1)
    accept_categories: list[str] = []
    wanted_items: str = ""  # free-text — kept for backward compatibility
    wanted_categories: list[str] = []
    wanted_subcategories: list[str] = []
    wanted_brands: list[str] = []
    wanted_locations: list[str] = []
    wanted_value_min: ValueIn | None = None
    wanted_value_max: ValueIn | None = None
    value_gap_tolerance: int = 0
    chain_opt_in: bool = False
    trade_preference: str = "DIRECT_ONLY"
    min_value: ValueIn | None = None
    max_value: ValueIn | None = None
    photo_urls: list[str] = []


class ListingUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    wanted_items: str | None = None
    location: str | None = None
    category: str | None = None
    subcategory: str | None = None
    accept_categories: list[str] | None = None
    photo_urls: list[str] | None = None
    min_value: ValueIn | None = None
    max_value: ValueIn | None = None
    brand: str | None = None
    model_name: str | None = None
    attributes: dict[str, Any] | None = None
    wanted_categories: list[str] | None = None
    wanted_subcategories: list[str] | None = None
    wanted_brands: list[str] | None = None
    wanted_locations: list[str] | None = None
    wanted_value_min: ValueIn | None = None
    wanted_value_max: ValueIn | None = None
    value_gap_tolerance: int | None = None
    chain_opt_in: bool | None = None
    trade_preference: str | None = None
    location_city: str | None = None
    location_district: str | None = None
    location_country: str | None = None
    # Ignored / rejected if present — users cannot self-approve
    status: str | None = None
    moderation_status: str | None = None


class MatchingPreferencesIn(BaseModel):
    chain_opt_in: bool | None = None
    trade_preference: str | None = None
    max_chain_length: int | None = None


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


class ChainMatchIn(BaseModel):
    """Seed a chain search from one of the caller's listings."""

    listing_id: int | None = None
    # Legacy shape kept so disabled-flag clients still validate
    requested_listing_ids: list[int] = []
    offered_listing_ids: list[int] = []
    max_length: int | None = Field(default=None, ge=3, le=10)
    max_results: int = Field(default=10, ge=1, le=50)
    persist_proposals: bool = True


class ChainConsentIn(BaseModel):
    idempotency_key: str | None = None
    expected_version: int | None = None
    note: str = ""


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


def require_moderation_staff(user: Annotated[dict, Depends(require_user)]) -> dict:
    if user.get("role") not in MODERATION_STAFF_ROLES:
        raise HTTPException(
            403,
            detail={"code": "STAFF_REQUIRED", "message": "Yönetim paneli yetkisi gerekli"},
        )
    return user


class StaffRoleIn(BaseModel):
    role: str
    note: str = ""


class AssignmentIn(BaseModel):
    listing_id: int
    assignee_id: int
    note: str = ""


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
    # Public feed: APPROVED only — served via short-lived cache that invalidates on moderation
    cache_key = f"public:listings:{category or ''}:{q or ''}"
    cached = cache_get(cache_key)
    if cached is not None:
        # Hard filter: never leak non-approved even if cache stale/buggy
        safe = [
            x
            for x in cached.get("listings", [])
            if str(x.get("status", "")).upper() in {"APPROVED", "ACTIVE"}
        ]
        return {"listings": safe, "viewer": user["username"] if user else None, "cache": True}

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
    payload = {"listings": items}
    cache_set(cache_key, payload)
    return {"listings": items, "viewer": user["username"] if user else None, "cache": False}


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
    try:
        want = validate_structured_want(
            wanted_categories=body.wanted_categories,
            wanted_subcategories=body.wanted_subcategories,
            wanted_brands=body.wanted_brands,
            wanted_locations=body.wanted_locations,
            wanted_value_min=(
                _parse_value(body.wanted_value_min).mandal_units if body.wanted_value_min else 0
            ),
            wanted_value_max=(
                _parse_value(body.wanted_value_max).mandal_units if body.wanted_value_max else 0
            ),
        )
        gap_tol = validate_value_tolerance(body.value_gap_tolerance)
        offer_norm = normalize_offer_fields(
            category=body.category,
            subcategory=body.subcategory,
            brand=body.brand,
            model_name=body.model_name,
            condition=body.condition,
            location=body.location,
            location_city=body.location_city,
            location_district=body.location_district,
            location_country=body.location_country,
            mandal_units=total.mandal_units,
            attributes=body.attributes,
        )
    except WantValidationError as exc:
        raise HTTPException(400, detail={"code": exc.code, "message": exc.message}) from exc
    pref = (body.trade_preference or TradePreference.DIRECT_ONLY.value).upper()
    if pref not in {TradePreference.DIRECT_ONLY.value, TradePreference.CHAIN_ALLOWED.value}:
        raise HTTPException(
            400, detail={"code": "INVALID_PREFERENCE", "message": "trade_preference geçersiz"}
        )
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
                  moderation_version, created_at, updated_at, moderation_updated_at,
                  moderation_status, inventory_status, chain_opt_in, trade_preference,
                  brand, model_name, attributes,
                  wanted_categories, wanted_subcategories, wanted_brands, wanted_locations,
                  wanted_value_min, wanted_value_max, value_gap_tolerance,
                  location_city, location_district, location_country
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    user["id"],
                    body.title.strip(),
                    body.description.strip(),
                    offer_norm["category"],
                    offer_norm["subcategory"],
                    offer_norm["condition"],
                    offer_norm["location"],
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
                    "PENDING_MODERATION",
                    "AVAILABLE",
                    1 if body.chain_opt_in else 0,
                    pref,
                    offer_norm["brand"],
                    offer_norm["model_name"],
                    db.dumps(offer_norm["attributes"]),
                    db.dumps(want["wanted_categories"]),
                    db.dumps(want["wanted_subcategories"]),
                    db.dumps(want["wanted_brands"]),
                    db.dumps(want["wanted_locations"]),
                    want["wanted_value_min"],
                    want["wanted_value_max"],
                    gap_tol,
                    offer_norm["location_city"],
                    offer_norm["location_district"],
                    offer_norm["location_country"],
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
            db.sync_dual_status(conn, lid, legacy_status=str(row["status"]))
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
    if body.status is not None or body.moderation_status is not None:
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
            row = dict(row)
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
            subcategory = (
                body.subcategory.strip() if body.subcategory is not None else row["subcategory"]
            )
            photos = body.photo_urls if body.photo_urls is not None else db.loads(row["photo_urls"], [])
            accept_cats = (
                body.accept_categories
                if body.accept_categories is not None
                else db.loads(row["accept_categories"], [])
            )
            min_units = int(row.get("min_mandal_units") or 0)
            max_units = int(row.get("max_mandal_units") or 0)
            if body.min_value is not None:
                min_units = _parse_value(body.min_value).mandal_units
            if body.max_value is not None:
                max_units = _parse_value(body.max_value).mandal_units

            critical = False
            if body.title is not None and title != row["title"]:
                critical = True
            if body.description is not None and description != row["description"]:
                critical = True
            if body.category is not None and category != row["category"]:
                critical = True
            if body.subcategory is not None and subcategory != row["subcategory"]:
                critical = True
            if body.wanted_items is not None and wanted != row["wanted_items"]:
                critical = True
            if body.photo_urls is not None and photos != db.loads(row["photo_urls"], []):
                critical = True
            if body.accept_categories is not None and accept_cats != db.loads(
                row["accept_categories"], []
            ):
                critical = True
            if body.min_value is not None or body.max_value is not None:
                critical = True

            if critical:
                conn.execute(
                    """
                    UPDATE trade_listings
                    SET title=?, description=?, wanted_items=?, location=?, category=?,
                        subcategory=?, accept_categories=?, photo_urls=?,
                        min_mandal_units=?, max_mandal_units=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        title,
                        description,
                        wanted,
                        location,
                        category,
                        subcategory,
                        db.dumps(accept_cats),
                        db.dumps(photos),
                        min_units,
                        max_units,
                        time.time(),
                        listing_id,
                    ),
                )
                remoderate_after_edit(
                    conn, listing_id=listing_id, actor_id=user["id"], correlation_id=cid
                )
                invalidate_listing(listing_id)
            else:
                # Safe metadata (location only) without remotion
                conn.execute(
                    """
                    UPDATE trade_listings
                    SET title=?, description=?, wanted_items=?, location=?, category=?,
                        subcategory=?, accept_categories=?, photo_urls=?,
                        updated_at=?, version=version+1
                    WHERE id=? AND version=?
                    """,
                    (
                        title,
                        description,
                        wanted,
                        location,
                        category,
                        subcategory,
                        db.dumps(accept_cats),
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
def moderation_queue(user: Annotated[dict, Depends(require_moderation_staff)]) -> dict:
    """Onay kutusu — yönetici / onaycı / superadmin."""
    with db.connect() as conn:
        role = user.get("role")
        if role == UserRole.MODERATOR.value:
            # Moderators see assigned listings + unassigned pool
            rows = conn.execute(
                """
                SELECT DISTINCT l.*
                FROM trade_listings l
                LEFT JOIN moderation_assignments a
                  ON a.listing_id = l.id AND a.status IN ('OPEN','IN_PROGRESS')
                WHERE l.status IN (
                  'PENDING_MODERATION','AI_REVIEW','ADMIN_REVIEW',
                  'MODERATION_UNAVAILABLE','EDIT_REQUIRED','ESCALATED'
                )
                AND (a.assignee_id = ? OR a.id IS NULL)
                ORDER BY l.moderation_priority DESC, l.created_at ASC
                LIMIT 200
                """,
                (user["id"],),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM trade_listings
                WHERE status IN (
                  'PENDING_MODERATION','AI_REVIEW','ADMIN_REVIEW',
                  'MODERATION_UNAVAILABLE','EDIT_REQUIRED','ESCALATED'
                )
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
            assign = conn.execute(
                """
                SELECT a.*, u.username AS assignee_username
                FROM moderation_assignments a
                JOIN users u ON u.id = a.assignee_id
                WHERE a.listing_id = ? AND a.status IN ('OPEN','IN_PROGRESS')
                ORDER BY a.id DESC LIMIT 1
                """,
                (d["id"],),
            ).fetchone()
            pub = _listing_public(conn, d, include_moderation=True)
            pub["owner_history"] = {
                "user_risk_score": (owner["user_risk_score"] if owner else 0),
                "change_score": (owner["change_score"] if owner else 0),
            }
            pub["prior_decisions"] = [dict(x) for x in decisions]
            pub["photo_moderation"] = [dict(x) for x in photos]
            pub["assignment"] = dict(assign) if assign else None
            items.append(pub)
        return {
            "queue": items,
            "count": len(items),
            "panel": "CHANGE_X_ADMIN",
            "actor_role": role,
        }


@app.post("/api/admin/moderation/{listing_id}/decision")
def moderation_decision_api(
    listing_id: int,
    body: ModerationDecisionIn,
    request: Request,
    user: Annotated[dict, Depends(require_moderation_staff)],
) -> dict:
    with db.connect() as conn:
        try:
            with db.immediate_tx(conn):
                row = apply_moderation_decision(
                    conn,
                    listing_id=listing_id,
                    actor_id=int(user["id"]),
                    actor_role=str(user["role"]),
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
    user: Annotated[dict, Depends(require_moderation_staff)],
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
    user: Annotated[dict, Depends(require_admin)],
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


@app.get("/api/admin/staff")
def admin_staff_list(user: Annotated[dict, Depends(require_admin)]) -> dict:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, suspended, change_score, user_risk_score, created_at
            FROM users
            WHERE role IN ('moderator','admin','superadmin')
            ORDER BY
              CASE role WHEN 'superadmin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
              username
            """
        ).fetchall()
        return {
            "staff": [dict(r) for r in rows],
            "assignable_roles": sorted(ASSIGNABLE_ROLES),
        }


@app.get("/api/admin/users")
def admin_users_search(
    user: Annotated[dict, Depends(require_admin)],
    q: str = "",
    limit: int = 50,
) -> dict:
    limit = max(1, min(int(limit), 100))
    with db.connect() as conn:
        if q.strip():
            rows = conn.execute(
                """
                SELECT id, username, role, suspended, change_score, created_at
                FROM users
                WHERE username LIKE ? COLLATE NOCASE
                ORDER BY username LIMIT ?
                """,
                (f"%{q.strip()}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, username, role, suspended, change_score, created_at
                FROM users ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"users": [dict(r) for r in rows]}


@app.post("/api/admin/users/{user_id}/role")
def admin_assign_role(
    user_id: int,
    body: StaffRoleIn,
    request: Request,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict:
    """Superadmin: assign yönetici / onaycı / user roles (unlimited)."""
    role = (body.role or "").strip().lower()
    if role == UserRole.SUPERADMIN.value:
        raise HTTPException(
            400,
            detail={
                "code": "ROLE_FORBIDDEN",
                "message": "Başka kullanıcıya superadmin atanamaz",
            },
        )
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            400,
            detail={"code": "INVALID_ROLE", "message": f"Geçersiz rol: {role}"},
        )
    with db.connect() as conn:
        target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "Kullanıcı yok"})
        if str(target["role"]) == UserRole.SUPERADMIN.value and int(target["id"]) != int(user["id"]):
            raise HTTPException(
                403,
                detail={"code": "PROTECTED", "message": "Superadmin rolü değiştirilemez"},
            )
        with db.immediate_tx(conn):
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            db.audit(
                conn,
                actor_id=user["id"],
                action="admin.assign_role",
                entity="user",
                entity_id=user_id,
                detail=db.dumps({"role": role, "note": body.note}),
                correlation_id=_cid(request),
            )
        row = conn.execute(
            "SELECT id, username, role, suspended, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return {"user": dict(row)}


@app.post("/api/admin/assignments")
def admin_create_assignment(
    body: AssignmentIn,
    request: Request,
    user: Annotated[dict, Depends(require_admin)],
) -> dict:
    """Yönetici / Superadmin: onaycıya takas ilanı görevi ata."""
    with db.connect() as conn:
        listing = conn.execute(
            "SELECT * FROM trade_listings WHERE id = ?", (body.listing_id,)
        ).fetchone()
        if not listing:
            raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND", "message": "İlan yok"})
        assignee = conn.execute("SELECT * FROM users WHERE id = ?", (body.assignee_id,)).fetchone()
        if not assignee:
            raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "Atanan yok"})
        if str(assignee["role"]) not in MODERATION_STAFF_ROLES:
            raise HTTPException(
                400,
                detail={
                    "code": "NOT_STAFF",
                    "message": "Görev yalnızca yönetici/onaycıya atanabilir",
                },
            )
        now = time.time()
        with db.immediate_tx(conn):
            # Close prior open assignments for same listing
            conn.execute(
                """
                UPDATE moderation_assignments
                SET status = 'REASSIGNED', updated_at = ?
                WHERE listing_id = ? AND status IN ('OPEN','IN_PROGRESS')
                """,
                (now, body.listing_id),
            )
            cur = conn.execute(
                """
                INSERT INTO moderation_assignments(
                  listing_id, assignee_id, assigned_by, note, status, created_at, updated_at
                ) VALUES (?,?,?,?, 'OPEN', ?, ?)
                """,
                (
                    body.listing_id,
                    body.assignee_id,
                    user["id"],
                    (body.note or "")[:300],
                    now,
                    now,
                ),
            )
            aid = int(cur.lastrowid)
            db.audit(
                conn,
                actor_id=user["id"],
                action="admin.assign_task",
                entity="listing",
                entity_id=body.listing_id,
                detail=db.dumps(
                    {"assignment_id": aid, "assignee_id": body.assignee_id, "note": body.note}
                ),
                correlation_id=_cid(request),
            )
        row = conn.execute("SELECT * FROM moderation_assignments WHERE id = ?", (aid,)).fetchone()
        return {"assignment": dict(row)}


@app.get("/api/admin/assignments/mine")
def admin_my_assignments(user: Annotated[dict, Depends(require_moderation_staff)]) -> dict:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT a.*, l.title, l.status AS listing_status, l.category, l.risk_level
            FROM moderation_assignments a
            JOIN trade_listings l ON l.id = a.listing_id
            WHERE a.assignee_id = ? AND a.status IN ('OPEN','IN_PROGRESS')
            ORDER BY a.created_at DESC
            LIMIT 100
            """,
            (user["id"],),
        ).fetchall()
        return {"assignments": [dict(r) for r in rows], "count": len(rows)}


@app.get("/api/admin/panel")
def admin_panel_bootstrap(user: Annotated[dict, Depends(require_moderation_staff)]) -> dict:
    """Separate yönetim paneli bootstrap — kullanıcı uygulamasından bağımsız."""
    with db.connect() as conn:
        pending = conn.execute(
            """
            SELECT COUNT(*) c FROM trade_listings
            WHERE status IN (
              'PENDING_MODERATION','AI_REVIEW','ADMIN_REVIEW',
              'MODERATION_UNAVAILABLE','EDIT_REQUIRED','ESCALATED'
            )
            """
        ).fetchone()["c"]
        mine = conn.execute(
            """
            SELECT COUNT(*) c FROM moderation_assignments
            WHERE assignee_id = ? AND status IN ('OPEN','IN_PROGRESS')
            """,
            (user["id"],),
        ).fetchone()["c"]
        return {
            "panel": "CHANGE_X_ADMIN",
            "actor": {
                "id": user["id"],
                "username": user.get("username"),
                "role": user.get("role"),
            },
            "capabilities": {
                "moderation_queue": True,
                "approve": True,
                "reject": True,
                "request_edit": True,
                "delete": True,
                "assign_tasks": user.get("role")
                in {UserRole.ADMIN.value, UserRole.SUPERADMIN.value},
                "assign_roles": user.get("role") == UserRole.SUPERADMIN.value,
                "unlimited": user.get("role") == UserRole.SUPERADMIN.value,
            },
            "stats": {"pending_moderation": pending, "my_open_tasks": mine},
            "actions": ["APPROVE", "REJECT", "REQUEST_EDIT", "DELETE"],
        }



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
        "wanted_categories": db.loads(row.get("wanted_categories") or "[]", []),
        "wanted_subcategories": db.loads(row.get("wanted_subcategories") or "[]", []),
        "wanted_brands": db.loads(row.get("wanted_brands") or "[]", []),
        "wanted_locations": db.loads(row.get("wanted_locations") or "[]", []),
        "wanted_value_min": int(row.get("wanted_value_min") or 0),
        "wanted_value_max": int(row.get("wanted_value_max") or 0),
        "value_gap_tolerance": int(row.get("value_gap_tolerance") or 0),
        "brand": row.get("brand") or "",
        "model_name": row.get("model_name") or "",
        "attributes": db.loads(row.get("attributes") or "{}", {}),
        "chain_opt_in": bool(int(row.get("chain_opt_in") or 0)),
        "trade_preference": row.get("trade_preference") or "DIRECT_ONLY",
        "moderation_status": row.get("moderation_status"),
        "inventory_status": row.get("inventory_status"),
        "location_city": row.get("location_city") or "",
        "location_district": row.get("location_district") or "",
        "location_country": row.get("location_country") or "",
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


# Change Chain Proposal Engine V1 — feature-flagged; no Asset Lock settlement
@app.post("/api/change-chain/match")
def change_chain_match(
    body: ChainMatchIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    if not matching_config.change_chain_enabled():
        raise HTTPException(
            501,
            detail={
                "code": "CHANGE_CHAIN_DISABLED",
                "message": "Change Chain feature flag kapalı",
                "feature_flag": "CHANGE_CHAIN_ENABLED=false",
            },
        )
    seed_id = body.listing_id
    if seed_id is None:
        # Prefer caller's offered listing as seed when using legacy shape
        seed_id = (body.offered_listing_ids or body.requested_listing_ids or [None])[0]
    if seed_id is None:
        raise HTTPException(
            400,
            detail={"code": "SEED_REQUIRED", "message": "listing_id gerekli"},
        )
    try:
        with db.connect() as conn:
            with db.immediate_tx(conn):
                result = run_chain_match(
                    conn,
                    seed_listing_id=int(seed_id),
                    actor_id=int(user["id"]),
                    max_length=body.max_length,
                    max_results=body.max_results,
                    persist=body.persist_proposals,
                )
                db.audit(
                    conn,
                    actor_id=user["id"],
                    action="chain.match",
                    entity="chain",
                    entity_id=None,
                    detail=db.dumps(
                        {
                            "seed": seed_id,
                            "cycles": result.get("cycle_count"),
                            "proposals": len(result.get("proposals") or []),
                        }
                    ),
                    correlation_id=_cid(request),
                )
                return result
    except ChainEngineError as exc:
        raise HTTPException(
            exc.http_status, detail={"code": exc.code, "message": exc.message}
        ) from exc


@app.get("/api/change-chain/proposals")
def change_chain_proposals_list(user: Annotated[dict, Depends(require_user)]) -> dict:
    if not matching_config.change_chain_enabled():
        raise HTTPException(
            501,
            detail={
                "code": "CHANGE_CHAIN_DISABLED",
                "message": "Change Chain feature flag kapalı",
            },
        )
    with db.connect() as conn:
        items = list_proposals_for_user(conn, int(user["id"]))
        return {"proposals": items, "count": len(items)}


@app.get("/api/change-chain/proposals/{proposal_id}")
def change_chain_proposal_detail(
    proposal_id: int,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    if not matching_config.change_chain_enabled():
        raise HTTPException(
            501,
            detail={
                "code": "CHANGE_CHAIN_DISABLED",
                "message": "Change Chain feature flag kapalı",
            },
        )
    try:
        with db.connect() as conn:
            prop = proposal_public(conn, proposal_id)
            if int(user["id"]) not in {int(x) for x in prop["owner_ids"]}:
                if user.get("role") not in {UserRole.ADMIN.value, UserRole.SUPERADMIN.value}:
                    raise HTTPException(
                        403, detail={"code": "FORBIDDEN", "message": "Yetkisiz"}
                    )
            return prop
    except ChainProposalError as exc:
        raise HTTPException(
            exc.http_status, detail={"code": exc.code, "message": exc.message}
        ) from exc


@app.post("/api/change-chain/proposals/{proposal_id}/accept")
def change_chain_proposal_accept(
    proposal_id: int,
    body: ChainConsentIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    if not matching_config.change_chain_enabled():
        raise HTTPException(
            501,
            detail={
                "code": "CHANGE_CHAIN_DISABLED",
                "message": "Change Chain feature flag kapalı",
            },
        )
    try:
        with db.connect() as conn:
            with db.immediate_tx(conn):
                result = accept_proposal(
                    conn,
                    proposal_id,
                    actor_id=int(user["id"]),
                    actor_role=str(user.get("role") or "user"),
                    expected_version=body.expected_version,
                    idempotency_key=body.idempotency_key,
                )
                db.audit(
                    conn,
                    actor_id=user["id"],
                    action="chain.accept",
                    entity="chain_proposal",
                    entity_id=proposal_id,
                    detail=db.dumps({"status": result.get("status"), "settlement": "NOT_IMPLEMENTED"}),
                    correlation_id=_cid(request),
                )
                return result
    except ChainProposalError as exc:
        raise HTTPException(
            exc.http_status, detail={"code": exc.code, "message": exc.message}
        ) from exc


@app.post("/api/change-chain/proposals/{proposal_id}/reject")
def change_chain_proposal_reject(
    proposal_id: int,
    body: ChainConsentIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    if not matching_config.change_chain_enabled():
        raise HTTPException(
            501,
            detail={
                "code": "CHANGE_CHAIN_DISABLED",
                "message": "Change Chain feature flag kapalı",
            },
        )
    try:
        with db.connect() as conn:
            with db.immediate_tx(conn):
                result = reject_proposal(
                    conn,
                    proposal_id,
                    actor_id=int(user["id"]),
                    actor_role=str(user.get("role") or "user"),
                    expected_version=body.expected_version,
                    idempotency_key=body.idempotency_key,
                )
                db.audit(
                    conn,
                    actor_id=user["id"],
                    action="chain.reject",
                    entity="chain_proposal",
                    entity_id=proposal_id,
                    detail=db.dumps({"status": result.get("status")}),
                    correlation_id=_cid(request),
                )
                return result
    except ChainProposalError as exc:
        raise HTTPException(
            exc.http_status, detail={"code": exc.code, "message": exc.message}
        ) from exc


@app.get("/api/matching/preferences")
def get_matching_preferences(user: Annotated[dict, Depends(require_user)]) -> dict:
    with db.connect() as conn:
        prefs = get_user_preferences(conn, int(user["id"]))
        view = public_preferences_view(prefs)
        # Privacy: never attach email/phone/username secrets beyond preference flags
        assert "password" not in view
        assert "email" not in view
        assert "phone" not in view
        return {
            "preferences": view,
            "feature_flags": {
                "CHANGE_CHAIN_ENABLED": matching_config.change_chain_enabled(),
            },
            "compatibility_policy": get_compatibility().policy_version,
        }


@app.patch("/api/matching/preferences")
def patch_matching_preferences(
    body: MatchingPreferencesIn,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    try:
        with db.connect() as conn:
            with db.immediate_tx(conn):
                prefs = set_user_preferences(
                    conn,
                    int(user["id"]),
                    chain_opt_in=body.chain_opt_in,
                    trade_preference=body.trade_preference,
                    max_chain_length=body.max_chain_length,
                )
                db.audit(
                    conn,
                    actor_id=user["id"],
                    action="matching.preferences.update",
                    entity="user",
                    entity_id=user["id"],
                    detail=db.dumps(public_preferences_view(prefs)),
                    correlation_id=_cid(request),
                )
            return {
                "preferences": public_preferences_view(prefs),
                "feature_flags": {
                    "CHANGE_CHAIN_ENABLED": matching_config.change_chain_enabled()
                },
            }
    except ValueError as exc:
        raise HTTPException(
            400, detail={"code": "INVALID_PREFERENCE", "message": str(exc)}
        ) from exc


@app.get("/api/listings/{listing_id}/matchability")
def listing_matchability(
    listing_id: int,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND", "message": "Bulunamadı"})
        d = dict(row)
        if int(d["owner_id"]) != user["id"] and user.get("role") not in {
            UserRole.ADMIN.value,
            UserRole.SUPERADMIN.value,
        }:
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yetkisiz"})
        prefs = get_user_preferences(conn, int(d["owner_id"]))
        return matchability_report(d, user_pref=prefs.get("trade_preference"))


@app.post("/api/uploads/image")
async def upload_listing_image(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    file: UploadFile = File(...),
) -> dict:
    """Upload a listing photo; returns a public /uploads/... URL (no money)."""
    _rate_limit(request, limit=30, endpoint="/api/uploads/image", user_id=int(user["id"]))
    content_type = (file.content_type or "").lower().strip()
    ext = ALLOWED_IMAGE_TYPES.get(content_type)
    if not ext:
        # Fallback by filename
        name = (file.filename or "").lower()
        if name.endswith((".jpg", ".jpeg")):
            ext = ".jpg"
        elif name.endswith(".png"):
            ext = ".png"
        elif name.endswith(".webp"):
            ext = ".webp"
        elif name.endswith(".gif"):
            ext = ".gif"
        else:
            raise HTTPException(
                400,
                detail={
                    "code": "INVALID_IMAGE",
                    "message": "Yalnızca JPG/PNG/WEBP/GIF yükleyebilirsiniz",
                },
            )
    raw = await file.read()
    if not raw:
        raise HTTPException(400, detail={"code": "EMPTY_FILE", "message": "Boş dosya"})
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(
            400,
            detail={"code": "FILE_TOO_LARGE", "message": "Görsel en fazla 8 MB olabilir"},
        )
    # Basic magic-byte sniff
    if not (
        raw.startswith(b"\xff\xd8\xff")  # jpeg
        or raw.startswith(b"\x89PNG\r\n\x1a\n")  # png
        or raw.startswith(b"GIF87a")
        or raw.startswith(b"GIF89a")
        or raw.startswith(b"RIFF")  # webp container
    ):
        raise HTTPException(
            400,
            detail={"code": "INVALID_IMAGE", "message": "Geçersiz görsel içeriği"},
        )
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / fname
    path.write_bytes(raw)
    url = f"/uploads/{fname}"
    with db.connect() as conn:
        db.audit(
            conn,
            actor_id=user["id"],
            action="upload.image",
            entity="upload",
            entity_id=None,
            detail=db.dumps({"url": url, "bytes": len(raw), "content_type": content_type}),
            correlation_id=_cid(request),
        )
    return {"url": url, "bytes": len(raw), "content_type": content_type or f"image/{ext[1:]}"}


def _web_root() -> Path | None:
    if (WEB_DIR / "index.html").exists():
        return WEB_DIR
    if (ALT_WEB / "index.html").exists():
        return ALT_WEB
    return None


# Uploaded listing photos (before catch-all web mount)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

_static = _web_root()
if _static is not None:
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="web")
