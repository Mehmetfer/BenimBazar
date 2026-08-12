from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .states import InvalidTransition, TradeState, transition
from .value import difference, from_mandal, to_mandal

WEB_DIR = Path(__file__).resolve().parents[2] / "changex_app" / "build" / "web"
# Also allow serving from the live Flutter build used in this environment
ALT_WEB = Path("/home/ubuntu/varmisin-app/build/web")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="CHANGE X", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory rate limit: ip -> [timestamps]
_RATE: dict[str, list[float]] = {}


def _rate_limit(request: Request, limit: int = 60, window: float = 60.0) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = [t for t in _RATE.get(ip, []) if now - t < window]
    if len(bucket) >= limit:
        raise HTTPException(429, "Çok fazla istek")
    bucket.append(now)
    _RATE[ip] = bucket


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


class OfferCreateIn(BaseModel):
    listing_id: int
    offer_items: list[ListingItemIn] = Field(min_length=1)
    idempotency_key: str | None = None


class TransitionIn(BaseModel):
    target_state: TradeState
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
    with db._connect() as conn:
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
        raise HTTPException(401, "Giriş gerekli")
    return user


def require_admin(user: Annotated[dict, Depends(require_user)]) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin yetkisi gerekli")
    return user


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": "CHANGE X",
        "real_money": False,
        "units": ["Mandal", "Dirhem", "Madalyon"],
    }


@app.post("/api/auth/register")
def register(body: RegisterIn, request: Request) -> dict:
    _rate_limit(request, limit=20)
    username = body.username.strip()
    with db._connect() as conn:
        exists = conn.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if exists:
            raise HTTPException(409, "Bu kullanıcı adı alınmış")
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES (?,?,?)",
            (username, db.hash_password(body.password), time.time()),
        )
        uid = cur.lastrowid
        token = _new_session(conn, uid)
        db.audit(conn, uid, "register", username)
        return {"token": token, "user": {"id": uid, "username": username, "role": "user"}}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request) -> dict:
    _rate_limit(request, limit=30)
    with db._connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (body.username.strip(),),
        ).fetchone()
        if not row or not db.verify_password(body.password, row["password_hash"]):
            raise HTTPException(401, "Kullanıcı veya şifre hatalı")
        token = _new_session(conn, row["id"])
        db.audit(conn, row["id"], "login", row["username"])
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
        raise HTTPException(401, "Giriş gerekli")
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "change_score": user["change_score"],
    }


@app.post("/api/value/normalize")
def normalize_value(body: ValueIn) -> dict:
    total = to_mandal(madalyon=body.madalyon, dirhem=body.dirhem, mandal=body.mandal)
    return from_mandal(total).as_dict()


@app.get("/api/listings")
def list_listings(
    q: str | None = None,
    category: str | None = None,
    user: Annotated[dict | None, Depends(current_user)] = None,
) -> dict:
    sql = "SELECT * FROM trade_listings WHERE status = 'active'"
    args: list[Any] = []
    if category:
        sql += " AND category = ?"
        args.append(category)
    if q:
        sql += " AND (title LIKE ? OR description LIKE ? OR wanted_items LIKE ?)"
        like = f"%{q}%"
        args.extend([like, like, like])
    sql += " ORDER BY created_at DESC LIMIT 100"
    with db._connect() as conn:
        rows = conn.execute(sql, args).fetchall()
        items = [_listing_public(conn, dict(r)) for r in rows]
    return {"listings": items, "viewer": user["username"] if user else None}


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int) -> dict:
    with db._connect() as conn:
        row = conn.execute(
            "SELECT * FROM trade_listings WHERE id = ?", (listing_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Takas kaydı bulunamadı")
        return _listing_public(conn, dict(row))


@app.post("/api/listings")
def create_listing(
    body: ListingCreateIn,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    item_totals = [
        (it.name, to_mandal(**it.value.model_dump())) for it in body.items
    ]
    total = sum(v for _, v in item_totals)
    if total <= 0:
        raise HTTPException(400, "Takas değeri sıfır olamaz")
    min_v = to_mandal(**(body.min_value or ValueIn()).model_dump()) if body.min_value else 0
    max_v = to_mandal(**(body.max_value or ValueIn()).model_dump()) if body.max_value else total
    with db._connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO trade_listings(
              owner_id, title, description, category, subcategory, condition,
              location, value_mandal, accept_categories, wanted_items,
              min_value_mandal, max_value_mandal, photo_urls, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user["id"],
                body.title.strip(),
                body.description.strip(),
                body.category.strip(),
                body.subcategory.strip(),
                body.condition,
                body.location.strip(),
                total,
                db.dumps(body.accept_categories),
                body.wanted_items.strip(),
                min_v,
                max_v,
                db.dumps(body.photo_urls),
                time.time(),
            ),
        )
        lid = cur.lastrowid
        for name, val in item_totals:
            conn.execute(
                "INSERT INTO listing_items(listing_id, name, value_mandal) VALUES (?,?,?)",
                (lid, name, val),
            )
        db.audit(conn, user["id"], "listing.create", f"id={lid}")
        row = conn.execute("SELECT * FROM trade_listings WHERE id = ?", (lid,)).fetchone()
        return _listing_public(conn, dict(row))


@app.post("/api/trades/offer")
def create_offer(
    body: OfferCreateIn,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db._connect() as conn:
        listing = conn.execute(
            "SELECT * FROM trade_listings WHERE id = ? AND status = 'active'",
            (body.listing_id,),
        ).fetchone()
        if not listing:
            raise HTTPException(404, "Takas kaydı bulunamadı")
        if listing["owner_id"] == user["id"]:
            raise HTTPException(400, "Kendi kaydına teklif veremezsin")

        if body.idempotency_key:
            existing = conn.execute(
                "SELECT * FROM trades WHERE idempotency_key = ?",
                (body.idempotency_key,),
            ).fetchone()
            if existing:
                return _trade_public(dict(existing))

        b_total = sum(to_mandal(**it.value.model_dump()) for it in body.offer_items)
        if b_total <= 0:
            raise HTTPException(400, "Teklif değeri sıfır olamaz")
        a_total = int(listing["value_mandal"])
        gap = a_total - b_total
        now = time.time()
        cur = conn.execute(
            """
            INSERT INTO trades(
              listing_id, initiator_id, counterparty_id, state,
              a_value_mandal, b_value_mandal, gap_mandal, idempotency_key,
              created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                body.listing_id,
                user["id"],
                listing["owner_id"],
                TradeState.OFFERED.value,
                a_total,
                b_total,
                gap,
                body.idempotency_key,
                now,
                now,
            ),
        )
        tid = cur.lastrowid
        conn.execute(
            """
            INSERT INTO trade_events(trade_id, actor_id, from_state, to_state, note, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (tid, user["id"], None, TradeState.OFFERED.value, "Teklif oluşturuldu", now),
        )
        db.audit(conn, user["id"], "trade.offer", f"trade={tid}")
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (tid,)).fetchone()
        result = _trade_public(dict(trade))
        result["match"] = difference(a_total, b_total)
        return result


@app.post("/api/trades/{trade_id}/transition")
def trade_transition(
    trade_id: int,
    body: TransitionIn,
    user: Annotated[dict, Depends(require_user)],
) -> dict:
    with db._connect() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise HTTPException(404, "Takas bulunamadı")
        if user["id"] not in (trade["initiator_id"], trade["counterparty_id"]) and user["role"] != "admin":
            raise HTTPException(403, "Bu takasa erişimin yok")
        current = TradeState(trade["state"])
        try:
            new_state = transition(current, body.target_state)
        except InvalidTransition as exc:
            raise HTTPException(400, str(exc)) from exc
        now = time.time()
        conn.execute(
            "UPDATE trades SET state = ?, updated_at = ? WHERE id = ?",
            (new_state.value, now, trade_id),
        )
        conn.execute(
            """
            INSERT INTO trade_events(trade_id, actor_id, from_state, to_state, note, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (trade_id, user["id"], current.value, new_state.value, body.note, now),
        )
        db.audit(conn, user["id"], "trade.transition", f"{current.value}->{new_state.value}")
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return _trade_public(dict(row))


@app.get("/api/trades/mine")
def my_trades(user: Annotated[dict, Depends(require_user)]) -> dict:
    with db._connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM trades
            WHERE initiator_id = ? OR counterparty_id = ?
            ORDER BY updated_at DESC LIMIT 100
            """,
            (user["id"], user["id"]),
        ).fetchall()
        return {"trades": [_trade_public(dict(r)) for r in rows]}


@app.get("/api/admin/stats")
def admin_stats(user: Annotated[dict, Depends(require_admin)]) -> dict:
    with db._connect() as conn:
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        listings = conn.execute("SELECT COUNT(*) c FROM trade_listings").fetchone()["c"]
        trades = conn.execute("SELECT COUNT(*) c FROM trades").fetchone()["c"]
        return {"users": users, "listings": listings, "trades": trades, "real_money": False}


def _listing_public(conn, row: dict) -> dict:
    items = conn.execute(
        "SELECT name, value_mandal FROM listing_items WHERE listing_id = ?",
        (row["id"],),
    ).fetchall()
    owner = conn.execute(
        "SELECT username, change_score FROM users WHERE id = ?", (row["owner_id"],)
    ).fetchone()
    value = from_mandal(int(row["value_mandal"])).as_dict()
    import json

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "subcategory": row["subcategory"],
        "condition": row["condition"],
        "location": row["location"],
        "value": value,
        "accept_categories": json.loads(row["accept_categories"] or "[]"),
        "wanted_items": row["wanted_items"],
        "min_value": from_mandal(int(row["min_value_mandal"])).as_dict(),
        "max_value": from_mandal(int(row["max_value_mandal"])).as_dict(),
        "photo_urls": json.loads(row["photo_urls"] or "[]"),
        "items": [
            {"name": i["name"], "value": from_mandal(int(i["value_mandal"])).as_dict()}
            for i in items
        ],
        "owner": {
            "id": row["owner_id"],
            "username": owner["username"] if owner else "?",
            "change_score": owner["change_score"] if owner else 0,
        },
        "created_at": row["created_at"],
    }


def _trade_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "listing_id": row["listing_id"],
        "initiator_id": row["initiator_id"],
        "counterparty_id": row["counterparty_id"],
        "state": row["state"],
        "a_value": from_mandal(int(row["a_value_mandal"])).as_dict(),
        "b_value": from_mandal(int(row["b_value_mandal"])).as_dict(),
        "gap": from_mandal(abs(int(row["gap_mandal"]))).as_dict(),
        "gap_mandal": row["gap_mandal"],
        "exact_match": row["gap_mandal"] == 0,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "settlement_note": "Fark gerçek para ile kapatılamaz.",
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
