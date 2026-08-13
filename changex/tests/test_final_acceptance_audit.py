"""FINAL autonomous acceptance — 10 listing E2E + messaging + RBAC/security evidence.

Uses isolated pytest tmp DB (does not touch production changex/data).
Writes reports/acceptance artifacts when run.
"""

from __future__ import annotations

from pathlib import Path

from changex.app.db import DEFAULT_SUPERADMIN_PASSWORD, DEFAULT_SUPERADMIN_USERNAME
from changex.tests.helpers import auth, promote_admin, register

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
REPORT_DIR = Path(__file__).resolve().parents[2] / "reports" / "acceptance"
LISTINGS_REPORT = REPORT_DIR / "TEN_LISTINGS_ACCEPTANCE.md"
MSG_REPORT = REPORT_DIR / "MESSAGING_ACCEPTANCE.md"
RBAC_REPORT = REPORT_DIR / "RBAC_ACCEPTANCE.md"


def _sa(client):
    r = client.post(
        "/api/auth/login",
        json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _upload(client, token: str, name: str = "a.png") -> str:
    r = client.post(
        "/api/uploads/image",
        headers=auth(token),
        files={"file": (name, PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    return r.json()["url"]


def _create_listing(client, token: str, title: str, *, description: str, category: str, photo: str | None):
    payload = {
        "title": title,
        "description": description,
        "category": category,
        "items": [{"name": "Item", "value": {"madalyon": 1, "dirhem": 0, "mandal": 0}}],
        "photo_urls": [photo] if photo else [],
    }
    return client.post("/api/listings", headers=auth(token), json=payload)


def _approve(client, sa_token: str, listing_id: int):
    return client.post(
        f"/api/admin/moderation/{listing_id}/decision",
        headers=auth(sa_token),
        json={"decision": "APPROVE", "reason": "acceptance"},
    )


def _listing_ids(client) -> set[int]:
    r = client.get("/api/listings")
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("listings") or data.get("items") or []
    return {int(x["id"]) for x in items}


def test_final_acceptance_ten_listings_and_messaging_and_rbac(client, monkeypatch):
    """Full user journey evidence for FINAL_AUTONOMOUS_ACCEPTANCE_REPORT."""
    # High-volume acceptance journey: disable process rate limiter (still covered by dedicated rate tests).
    from changex.app import main as main_mod

    monkeypatch.setattr(main_mod, "_RATE", {})
    monkeypatch.setattr(main_mod, "_rate_limit", lambda *a, **k: None)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    sa = _sa(client)
    sa_token = sa["token"]
    buyer = register(client, "acc_buyer")
    outsider = register(client, "acc_outsider")
    admin_u = register(client, "acc_admin")
    promote_admin(admin_u["user"]["id"])

    scenarios = [
        ("normal", "Normal İlan Acceptance", "Temiz açıklama", "Elektronik", True, "approve"),
        ("missing_title", "", "Eksik başlık", "Kitap", False, "reject_client"),
        ("long_desc", "Uzun Açıklama", "X" * 4000, "Ev", True, "approve"),
        ("with_photo", "Görselli İlan", "Fotoğraf var", "Spor", True, "approve"),
        ("special_chars", "Özel <script>alert(1)</script> & 中文", "Güvenli metin", "Müzik", True, "approve"),
        ("boundary_cat", "Sınır Kategori", "Edge", "Diğer", True, "approve"),
        ("reject_flow", "Reddedilecek", "Uygunsuz örnek içerik spam", "Oyuncak", True, "reject"),
        ("duplicate_a", "Duplicate Title Twin", "İlk kopya", "Giyim", True, "approve"),
        ("duplicate_b", "Duplicate Title Twin", "İkinci kopya", "Giyim", True, "approve"),
        ("malicious_input", "'; DROP TABLE users;--", "'; OR 1=1 --", "Bahçe", True, "approve"),
    ]

    listing_rows = []
    approved_ids: list[int] = []

    for i, (key, title, desc, cat, want_photo, outcome) in enumerate(scenarios, start=1):
        seller = register(client, f"acc_seller_{i:02d}")
        photo = _upload(client, seller["token"], f"s{i}.png") if want_photo else None
        created = _create_listing(
            client, seller["token"], title, description=desc, category=cat, photo=photo
        )

        row = {
            "n": i,
            "key": key,
            "title": title[:60],
            "create": "FAIL",
            "pending": "N/A",
            "moderation": "N/A",
            "public": "N/A",
            "message": "N/A",
            "result": "FAIL",
            "listing_id": None,
            "seller_token": seller["token"],
            "seller_id": seller["user"]["id"],
        }

        if outcome == "reject_client":
            assert created.status_code in {400, 422}, created.text
            row.update(create="REJECTED_CLIENT", result="PASS")
            listing_rows.append(row)
            continue

        assert created.status_code == 200, created.text
        body = created.json()
        lid = int(body["id"])
        row["listing_id"] = lid
        row["create"] = "PASS"
        status = str(body.get("status") or "").upper()
        assert status in {"PENDING_MODERATION", "ADMIN_REVIEW", "PENDING"}, status
        row["pending"] = "PASS"

        assert lid not in _listing_ids(client)
        assert client.get(f"/api/listings/{lid}", headers=auth(buyer["token"])).status_code == 404

        if outcome == "reject":
            rej = client.post(
                f"/api/admin/moderation/{lid}/decision",
                headers=auth(sa_token),
                json={"decision": "REJECT", "reason": "acceptance reject"},
            )
            assert rej.status_code == 200, rej.text
            row["moderation"] = "REJECTED"
            assert lid not in _listing_ids(client)
            row["public"] = "HIDDEN_OK"
            row["result"] = "PASS"
            listing_rows.append(row)
            continue

        assert (
            client.post(
                f"/api/admin/moderation/{lid}/decision",
                headers=auth(buyer["token"]),
                json={"decision": "APPROVE", "reason": "nope"},
            ).status_code
            == 403
        )

        ap = _approve(client, sa_token, lid)
        assert ap.status_code == 200, ap.text
        row["moderation"] = "APPROVED"

        detail = client.get(f"/api/listings/{lid}")
        assert detail.status_code == 200, detail.text
        assert lid in _listing_ids(client)
        row["public"] = "PASS"
        approved_ids.append(lid)
        row["result"] = "PASS"
        listing_rows.append(row)

    msg_rows = []
    for idx, lid in enumerate(approved_ids[:3], start=1):
        start = client.post(
            "/api/messages/conversations",
            headers=auth(buyer["token"]),
            json={"listing_id": lid},
        )
        assert start.status_code == 200, start.text
        conv = start.json()
        cid = conv["id"]
        assert (
            client.get(
                f"/api/messages/conversations/{cid}/messages",
                headers=auth(outsider["token"]),
            ).status_code
            == 403
        )
        send = client.post(
            f"/api/messages/conversations/{cid}/messages",
            headers=auth(buyer["token"]),
            json={"body": f"Merhaba acceptance {idx} — telefon gerekmez"},
        )
        assert send.status_code == 200, send.text
        seller_token = None
        for r in listing_rows:
            if r["listing_id"] == lid:
                seller_token = r["seller_token"]
                break
        assert seller_token is not None
        inbox = client.get("/api/messages/inbox", headers=auth(seller_token))
        assert inbox.status_code == 200
        assert any(c["id"] == cid for c in inbox.json()["conversations"])
        reply = client.post(
            f"/api/messages/conversations/{cid}/messages",
            headers=auth(seller_token),
            json={"body": f"Cevap {idx}"},
        )
        assert reply.status_code == 200, reply.text
        again = client.get(
            f"/api/messages/conversations/{cid}/messages",
            headers=auth(buyer["token"]),
        )
        bodies = [m["body"] for m in again.json()["messages"]]
        assert any("telefon gerekmez" in b for b in bodies)
        assert any(f"Cevap {idx}" in b for b in bodies)
        mid = send.json()["id"]
        assert client.delete(f"/api/messages/{mid}", headers=auth(outsider["token"])).status_code == 403
        assert client.delete(f"/api/messages/{mid}", headers=auth(buyer["token"])).status_code == 200
        msg_rows.append(
            {
                "n": idx,
                "listing_id": lid,
                "conversation_id": cid,
                "idor": "PASS",
                "roundtrip": "PASS",
                "soft_delete": "PASS",
                "result": "PASS",
            }
        )
        for r in listing_rows:
            if r["listing_id"] == lid:
                r["message"] = "PASS"

    target = next(r for r in listing_rows if r["listing_id"] in approved_ids)
    cancel = client.post(
        f"/api/listings/{target['listing_id']}/cancel",
        headers=auth(target["seller_token"]),
    )
    assert cancel.status_code == 200, cancel.text

    rbac = []
    a0 = client.get("/api/admin/dashboard")
    rbac.append(
        {
            "check": "anon_dashboard",
            "status": a0.status_code,
            "expect": 401,
            "pass": a0.status_code in {401, 403},
        }
    )
    u0 = client.get("/api/admin/dashboard", headers=auth(buyer["token"]))
    rbac.append(
        {
            "check": "user_dashboard",
            "status": u0.status_code,
            "expect": 403,
            "pass": u0.status_code == 403,
        }
    )
    esc = client.post(
        f"/api/admin/users/{buyer['user']['id']}/role",
        headers=auth(buyer["token"]),
        json={"role": "superadmin"},
    )
    rbac.append(
        {
            "check": "user_self_escalate",
            "status": esc.status_code,
            "expect": 403,
            "pass": esc.status_code == 403,
        }
    )
    adm = client.post(
        "/api/auth/login",
        json={"username": "acc_admin", "password": "pass12"},
    )
    assert adm.status_code == 200
    bad_role = client.post(
        f"/api/admin/users/{buyer['user']['id']}/role",
        headers=auth(adm.json()["token"]),
        json={"role": "superadmin"},
    )
    rbac.append(
        {
            "check": "admin_assign_superadmin",
            "status": bad_role.status_code,
            "expect": "403_or_400",
            "pass": bad_role.status_code in {400, 403},
        }
    )
    h = client.get("/api/health")
    hdr = h.headers
    rbac.append(
        {
            "check": "security_headers",
            "status": h.status_code,
            "expect": "nosniff+frame+csp",
            "pass": hdr.get("x-content-type-options") == "nosniff"
            and hdr.get("x-frame-options") == "DENY"
            and "default-src" in (hdr.get("content-security-policy") or ""),
        }
    )

    lines = [
        "# TEN LISTINGS ACCEPTANCE",
        "",
        "| # | Key | Create | Pending Hidden | Moderation | Public | Message | Result |",
        "|---|-----|--------|----------------|------------|--------|---------|--------|",
    ]
    for r in listing_rows:
        lines.append(
            f"| {r['n']} | {r['key']} | {r['create']} | {r['pending']} | {r['moderation']} | {r['public']} | {r['message']} | {r['result']} |"
        )
    passed = sum(1 for r in listing_rows if r["result"] == "PASS")
    lines += ["", f"**Score: {passed}/{len(listing_rows)} PASS**", ""]
    LISTINGS_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    mlines = [
        "# MESSAGING ACCEPTANCE",
        "",
        "| # | Listing | Conversation | IDOR | Roundtrip | Soft-delete | Result |",
        "|---|---------|--------------|------|-----------|-------------|--------|",
    ]
    for r in msg_rows:
        mlines.append(
            f"| {r['n']} | {r['listing_id']} | {r['conversation_id']} | {r['idor']} | {r['roundtrip']} | {r['soft_delete']} | {r['result']} |"
        )
    mlines += ["", f"**Score: {len(msg_rows)}/3 PASS**", ""]
    MSG_REPORT.write_text("\n".join(mlines) + "\n", encoding="utf-8")

    rlines = ["# RBAC ACCEPTANCE", "", "| Check | Status | Expect | Pass |", "|-------|--------|--------|------|"]
    for r in rbac:
        rlines.append(
            f"| {r['check']} | {r['status']} | {r['expect']} | {'PASS' if r['pass'] else 'FAIL'} |"
        )
    RBAC_REPORT.write_text("\n".join(rlines) + "\n", encoding="utf-8")

    assert passed == len(listing_rows)
    assert len(msg_rows) == 3
    assert all(r["pass"] for r in rbac)


def test_bootstrap_password_not_force_overwritten_by_default(client, tmp_db, monkeypatch):
    """Production safety: init_db must not reset an operator-changed bootstrap password."""
    from changex.app import db

    monkeypatch.delenv("CHANGEX_BOOTSTRAP_SUPERADMIN_FORCE_SYNC", raising=False)
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE username=? COLLATE NOCASE",
            (db.hash_password("OperatorChanged!99"), DEFAULT_SUPERADMIN_USERNAME),
        )
    db.init_db(tmp_db)
    assert (
        client.post(
            "/api/auth/login",
            json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": "OperatorChanged!99"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": DEFAULT_SUPERADMIN_USERNAME, "password": DEFAULT_SUPERADMIN_PASSWORD},
        ).status_code
        in {401, 403}
    )
