#!/usr/bin/env python3
"""Live server smoke for photo scenarios (API). UI must be checked separately."""
from __future__ import annotations
import json, sys, uuid
from pathlib import Path
import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
FX = Path(__file__).resolve().parent / "fixtures"

def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30)
    assert c.get("/api/health").status_code == 200
    u = f"smoke_{uuid.uuid4().hex[:8]}"
    reg = c.post("/api/auth/register", json={"username": u, "password": "pass12"})
    assert reg.status_code == 200, reg.text
    tok = reg.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/uploads/image", files={"file": ("x.png", FX.joinpath("sample.png").read_bytes(), "image/png")}).status_code == 401
    for name, code in [("not_image.txt", 400), ("corrupt.png", 400)]:
        r = c.post("/api/uploads/image", headers=h, files={"file": (name, (FX/name).read_bytes(), "image/png" if name.endswith("png") else "text/plain")})
        assert r.status_code == code, r.text
    urls = []
    for name, ct in [("sample.png", "image/png"), ("sample2.png", "image/png"), ("sample.jpg", "image/jpeg")]:
        up = c.post("/api/uploads/image", headers=h, files={"file": (name, (FX/name).read_bytes(), ct)})
        assert up.status_code == 200, up.text
        urls.append(up.json()["url"])
        assert c.get(urls[-1]).status_code == 200
    cr = c.post("/api/listings", headers=h, json={
        "title": "Smoke Photos", "description": "smoke", "category": "Elektronik",
        "photo_urls": urls,
        "items": [{"name": "x", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}],
    })
    assert cr.status_code == 200, cr.text
    print(json.dumps({"ok": True, "listing_id": cr.json()["id"], "photo_urls": urls, "user": u}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
