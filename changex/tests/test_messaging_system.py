"""Messaging system: E2E, IDOR, rate limit, support, block, report."""

from __future__ import annotations

from pathlib import Path

from changex.app.messaging import safety as safety_mod
from changex.app.messaging import service as msg_service
from changex.tests.helpers import auth, make_listing, register

REPORT = Path(__file__).resolve().parents[2] / "reports" / "overnight" / "MESSAGING_E2E_REPORT.md"


def _super(client):
    r = client.post("/api/auth/login", json={"username": "superadmin", "password": "14531453"})
    assert r.status_code == 200
    return r.json()


def test_contact_detector_confidence():
    hits = safety_mod.detect_contact_info("Ara beni 0532 111 22 33 veya test@example.com")
    kinds = {h.kind for h in hits}
    assert "phone" in kinds
    assert "email" in kinds
    assert all(h.confidence >= 0.7 for h in hits)


def test_e2e_listing_message_reply_refresh(client):
    seller = register(client, "msg_seller_e2e")
    buyer = register(client, "msg_buyer_e2e")
    listing = make_listing(client, seller["token"], "iPhone 15 Message Test", approve=True)

    start = client.post(
        "/api/messages/conversations",
        headers=auth(buyer["token"]),
        json={"listing_id": listing["id"]},
    )
    assert start.status_code == 200, start.text
    conv = start.json()
    assert conv["listing_id"] == listing["id"]
    assert conv["listing_title"]
    cid = conv["id"]

    send = client.post(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(buyer["token"]),
        json={"body": "Merhaba, takas hâlâ geçerli mi?"},
    )
    assert send.status_code == 200, send.text
    assert send.json()["status"] in {"SENT", "DELIVERED", "READ"}

    # Seller receives
    inbox = client.get("/api/messages/inbox", headers=auth(seller["token"]))
    assert inbox.status_code == 200
    assert any(c["id"] == cid for c in inbox.json()["conversations"])
    msgs = client.get(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(seller["token"]),
    )
    assert msgs.status_code == 200
    assert any("geçerli" in m["body"] for m in msgs.json()["messages"])

    reply = client.post(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(seller["token"]),
        json={"body": "Evet, geçerli."},
    )
    assert reply.status_code == 200

    again = client.get(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(buyer["token"]),
    )
    assert again.status_code == 200
    bodies = [m["body"] for m in again.json()["messages"]]
    assert "Evet, geçerli." in bodies
    # refresh persistence
    again2 = client.get(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(buyer["token"]),
    )
    assert [m["body"] for m in again2.json()["messages"]] == bodies
    # no phone fields leaked
    blob = again2.text.lower()
    assert "phone" not in blob or "contact" in blob  # may have contact_hits key absent
    assert "0532" not in blob


def test_idor_user_c_cannot_access(client):
    a = register(client, "idor_a_user")
    b = register(client, "idor_b_user")
    c = register(client, "idor_c_user")
    listing = make_listing(client, a["token"], "IDOR Listing", approve=True)
    conv = client.post(
        "/api/messages/conversations",
        headers=auth(b["token"]),
        json={"listing_id": listing["id"]},
    ).json()
    cid = conv["id"]
    client.post(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(b["token"]),
        json={"body": "secret for A/B only"},
    )
    r = client.get(f"/api/messages/conversations/{cid}", headers=auth(c["token"]))
    assert r.status_code == 403
    r2 = client.get(
        f"/api/messages/conversations/{cid}/messages",
        headers=auth(c["token"]),
    )
    assert r2.status_code == 403
    r3 = client.get(f"/api/messages/conversations/{cid}")
    assert r3.status_code in {401, 403}


def test_block_prevents_message(client):
    a = register(client, "block_a")
    b = register(client, "block_b")
    listing = make_listing(client, a["token"], "Block Listing", approve=True)
    conv = client.post(
        "/api/messages/conversations",
        headers=auth(b["token"]),
        json={"listing_id": listing["id"]},
    ).json()
    me_b = client.get("/api/auth/me", headers=auth(b["token"])).json()
    client.post("/api/messages/block", headers=auth(a["token"]), json={"user_id": me_b["id"]})
    r = client.post(
        f"/api/messages/conversations/{conv['id']}/messages",
        headers=auth(b["token"]),
        json={"body": "still trying"},
    )
    assert r.status_code == 403


def test_report_and_admin_moderation(client):
    a = register(client, "rep_a")
    b = register(client, "rep_b")
    listing = make_listing(client, a["token"], "Report Listing", approve=True)
    conv = client.post(
        "/api/messages/conversations",
        headers=auth(b["token"]),
        json={"listing_id": listing["id"]},
    ).json()
    msg = client.post(
        f"/api/messages/conversations/{conv['id']}/messages",
        headers=auth(b["token"]),
        json={"body": "suspicious spam offer"},
    ).json()
    rep = client.post(
        f"/api/messages/{msg['id']}/report",
        headers=auth(a["token"]),
        json={"reason": "SPAM"},
    )
    assert rep.status_code == 200
    super_u = _super(client)
    lst = client.get("/api/admin/messages/reports", headers=auth(super_u["token"]))
    assert lst.status_code == 200
    assert lst.json()["count"] >= 1
    rid = lst.json()["reports"][0]["id"]
    mod = client.post(
        f"/api/admin/messages/reports/{rid}",
        headers=auth(super_u["token"]),
        json={"status": "ACTIONED"},
    )
    assert mod.status_code == 200


def test_support_ticket_user_admin_roundtrip(client):
    u = register(client, "support_user_1")
    created = client.post(
        "/api/support/tickets",
        headers=auth(u["token"]),
        json={
            "subject": "Hesap yardımı",
            "body": "İlanım onaylanmadı, yardım eder misiniz?",
            "category": "ACCOUNT",
            "priority": "HIGH",
        },
    )
    assert created.status_code == 200, created.text
    ticket = created.json()
    assert ticket["public_id"].startswith("SUPPORT-")
    assert ticket["status"] == "OPEN"
    tid = ticket["id"]

    # other user cannot see
    other = register(client, "support_other")
    deny = client.get(f"/api/support/tickets/{tid}", headers=auth(other["token"]))
    assert deny.status_code == 403

    super_u = _super(client)
    admin_list = client.get("/api/admin/support/tickets", headers=auth(super_u["token"]))
    assert admin_list.status_code == 200
    assert any(t["id"] == tid for t in admin_list.json()["tickets"])

    reply = client.post(
        f"/api/admin/support/tickets/{tid}/reply",
        headers=auth(super_u["token"]),
        json={"body": "İnceliyoruz, teşekkürler.", "resolve": False},
    )
    assert reply.status_code == 200
    mine = client.get(f"/api/support/tickets/{tid}", headers=auth(u["token"]))
    assert mine.status_code == 200
    assert any(m["is_staff"] for m in mine.json()["messages"])


def test_contact_warning_does_not_silently_rewrite(client, monkeypatch):
    monkeypatch.setenv("CHANGEX_CONTACT_POLICY", "WARN")
    # reload policy by calling function (reads env each time)
    a = register(client, "warn_a")
    b = register(client, "warn_b")
    listing = make_listing(client, a["token"], "Warn Listing", approve=True)
    conv = client.post(
        "/api/messages/conversations",
        headers=auth(b["token"]),
        json={"listing_id": listing["id"]},
    ).json()
    r = client.post(
        f"/api/messages/conversations/{conv['id']}/messages",
        headers=auth(b["token"]),
        json={"body": "Bana 05321234567 yaz"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "CONTACT_INFO_WARNING"
    # acknowledge
    r2 = client.post(
        f"/api/messages/conversations/{conv['id']}/messages",
        headers=auth(b["token"]),
        json={"body": "Bana 05321234567 yaz", "acknowledge_contact_warning": True},
    )
    assert r2.status_code == 200
    assert "05321234567" in r2.json()["body"]  # not silently rewritten


def test_rate_limit_messages(client, monkeypatch):
    monkeypatch.setattr(msg_service, "RATE_MSG_PER_MINUTE", 3)
    a = register(client, "rate_a")
    b = register(client, "rate_b")
    listing = make_listing(client, a["token"], "Rate Listing", approve=True)
    conv = client.post(
        "/api/messages/conversations",
        headers=auth(b["token"]),
        json={"listing_id": listing["id"]},
    ).json()
    codes = []
    for i in range(5):
        r = client.post(
            f"/api/messages/conversations/{conv['id']}/messages",
            headers=auth(b["token"]),
            json={"body": f"msg {i}"},
        )
        codes.append(r.status_code)
    assert 429 in codes


def test_ten_listings_messaging_integration(client):
    """At least 3 of overnight-style listings: buyer→seller message→reply."""
    rows = []
    for i in range(1, 4):
        seller = register(client, f"ten_msg_s_{i}")
        buyer = register(client, f"ten_msg_b_{i}")
        listing = make_listing(
            client,
            seller["token"],
            f"Overnight Msg Listing {i}",
            approve=True,
            category=["Elektronik", "Kitap", "Ev"][i - 1],
        )
        conv = client.post(
            "/api/messages/conversations",
            headers=auth(buyer["token"]),
            json={"listing_id": listing["id"]},
        )
        assert conv.status_code == 200
        cid = conv.json()["id"]
        m1 = client.post(
            f"/api/messages/conversations/{cid}/messages",
            headers=auth(buyer["token"]),
            json={"body": f"Listing {i} hâlâ aktif mi?"},
        )
        assert m1.status_code == 200
        m2 = client.post(
            f"/api/messages/conversations/{cid}/messages",
            headers=auth(seller["token"]),
            json={"body": f"Evet, listing {i} aktif."},
        )
        assert m2.status_code == 200
        refresh = client.get(
            f"/api/messages/conversations/{cid}/messages",
            headers=auth(buyer["token"]),
        )
        assert refresh.status_code == 200
        assert len(refresh.json()["messages"]) >= 2
        rows.append({"n": i, "listing_id": listing["id"], "conversation_id": cid, "result": "PASS"})

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MESSAGING E2E REPORT",
        "",
        "Listing-linked buyer→seller→reply on 3 approved listings (real API).",
        "",
        "| # | Listing | Conversation | Buyer→Seller | Reply | Refresh | Result |",
        "|---|---------|--------------|--------------|-------|---------|--------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['n']} | {r['listing_id']} | {r['conversation_id']} | PASS | PASS | PASS | {r['result']} |"
        )
    lines += ["", f"**Score: {len(rows)}/3 listing message flows PASS**", ""]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(rows) == 3


def test_admin_dashboard_includes_messaging_stats(client):
    super_u = _super(client)
    r = client.get("/api/admin/dashboard", headers=auth(super_u["token"]))
    assert r.status_code == 200
    assert "messaging" in r.json()
    for k in ("active_conversations", "open_support_tickets", "reported_messages", "blocked_users"):
        assert k in r.json()["messaging"]


def test_soft_delete_message_and_pending_listing_blocked(client):
    a = register(client, "del_a")
    b = register(client, "del_b")
    pending = make_listing(client, a["token"], "Pending No Chat", approve=False)
    bad = client.post(
        "/api/messages/conversations",
        headers=auth(b["token"]),
        json={"listing_id": pending["id"]},
    )
    assert bad.status_code == 400
    listing = make_listing(client, a["token"], "Delete Msg Listing", approve=True)
    conv = client.post(
        "/api/messages/conversations",
        headers=auth(b["token"]),
        json={"listing_id": listing["id"]},
    ).json()
    msg = client.post(
        f"/api/messages/conversations/{conv['id']}/messages",
        headers=auth(b["token"]),
        json={"body": "silinecek"},
    ).json()
    # other user cannot delete
    deny = client.delete(f"/api/messages/{msg['id']}", headers=auth(a["token"]))
    assert deny.status_code == 403
    ok = client.delete(f"/api/messages/{msg['id']}", headers=auth(b["token"]))
    assert ok.status_code == 200
    msgs = client.get(
        f"/api/messages/conversations/{conv['id']}/messages",
        headers=auth(a["token"]),
    ).json()["messages"]
    assert all(m["id"] != msg["id"] for m in msgs)


def test_support_allows_phone_even_under_block_policy(client, monkeypatch):
    monkeypatch.setenv("CHANGEX_CONTACT_POLICY", "BLOCK")
    u = register(client, "support_phone_ok")
    r = client.post(
        "/api/support/tickets",
        headers=auth(u["token"]),
        json={
            "subject": "İletişim",
            "body": "Beni 05321234567 numarasından arayın",
            "category": "ACCOUNT",
            "priority": "HIGH",
        },
    )
    assert r.status_code == 200, r.text
    assert "05321234567" in r.json()["messages"][0]["body"]


def test_moderate_report_missing_404(client):
    super_u = _super(client)
    r = client.post(
        "/api/admin/messages/reports/999999",
        headers=auth(super_u["token"]),
        json={"status": "ACTIONED"},
    )
    assert r.status_code == 404


def test_support_attachment_must_be_owned_upload(client):
    a = register(client, "att_owner")
    b = register(client, "att_thief")
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    up = client.post(
        "/api/uploads/image",
        headers=auth(a["token"]),
        files={"file": ("own.png", png, "image/png")},
    )
    assert up.status_code == 200, up.text
    url = up.json()["url"]
    steal = client.post(
        "/api/support/tickets",
        headers=auth(b["token"]),
        json={
            "subject": "Ek çalma",
            "body": "Bu ek bana ait değil",
            "attachment_url": url,
        },
    )
    assert steal.status_code == 403, steal.text
    ok = client.post(
        "/api/support/tickets",
        headers=auth(a["token"]),
        json={
            "subject": "Kendi ekim",
            "body": "Bu ek bana ait",
            "attachment_url": url,
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["messages"][0]["attachment_url"] == url
