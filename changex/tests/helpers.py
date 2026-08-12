"""Shared helpers for CHANGE X tests (importable; fixtures live in conftest)."""

from __future__ import annotations

from changex.app import db


def register(client, username: str, password: str = "pass12"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_listing(client, token: str, title: str, madalyon: int = 1, category: str = "Elektronik"):
    r = client.post(
        "/api/listings",
        headers=auth(token),
        json={
            "title": title,
            "description": title,
            "category": category,
            "items": [{"name": title, "value": {"madalyon": madalyon, "dirhem": 0, "mandal": 0}}],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def promote_admin(user_id: int) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
