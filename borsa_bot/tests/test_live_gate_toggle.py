"""UI/runtime live gate can open and close without env restart."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trading_safety.live_gate import CONFIRM_PHRASE, LiveGateStore, is_live_broker_enabled


@pytest.fixture()
def gate_store(tmp_path: Path, monkeypatch):
    store = LiveGateStore(path=tmp_path / "live_gate.json")
    monkeypatch.setattr("trading_safety.live_gate.live_gate_store", store)
    return store


def test_gate_enable_disable_roundtrip(gate_store: LiveGateStore):
    assert gate_store.is_user_enabled() is False
    assert is_live_broker_enabled() is False
    snap = gate_store.enable(phrase=CONFIRM_PHRASE, confirmed_by="test")
    assert snap.user_enabled is True
    assert snap.broker_enabled is True
    assert snap.confirmed is True
    assert snap.can_send_live_orders is False  # no real adapter
    assert is_live_broker_enabled() is True
    closed = gate_store.disable(by="test")
    assert closed.user_enabled is False
    assert is_live_broker_enabled() is False


def test_gate_rejects_bad_phrase(gate_store: LiveGateStore):
    with pytest.raises(ValueError):
        gate_store.enable(phrase="nope", confirmed_by="test")


def test_live_enable_disable_api(tmp_path: Path, monkeypatch):
    store = LiveGateStore(path=tmp_path / "live_gate_api.json")
    monkeypatch.setattr("trading_safety.live_gate.live_gate_store", store)

    from dashboard.app import app

    client = TestClient(app)
    bad = client.post("/api/live/enable", json={"confirm": True, "phrase": "WRONG"})
    assert bad.status_code == 400

    on = client.post(
        "/api/live/enable",
        json={"confirm": True, "phrase": CONFIRM_PHRASE},
    )
    assert on.status_code == 200
    body = on.json()
    assert body["ok"] is True
    assert body["live_gate"]["open"] is True
    assert body["live_gate"]["can_send_live_orders"] is False
    assert body["execution_mode"] == "LIVE"

    st = client.get("/api/live/status")
    assert st.status_code == 200
    assert st.json()["open"] is True

    off = client.post("/api/live/disable")
    assert off.status_code == 200
    assert off.json()["live_gate"]["open"] is False
    assert off.json()["execution_mode"] == "PAPER"

    st2 = client.get("/api/live/status")
    assert st2.json()["open"] is False
