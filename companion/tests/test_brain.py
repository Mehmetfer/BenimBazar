from __future__ import annotations

import tempfile
from pathlib import Path

from companion.app.brain import Intent, process, process_deterministic, try_math
from companion.app.memory import MemoryStore, extract_memories


def test_math() -> None:
    assert try_math("12 + 5 kaç?") == "17"
    assert try_math("8 x 3") == "24"


def test_ai_first_greeting_and_market() -> None:
    greet = process("Merhaba", memories={"user_name": "Mehmet"}, prefer_llm=True)
    assert greet.intent == Intent.GREETING
    assert greet.use_llm is True
    assert "Mehmet" in (greet.reply or "")

    market = process("THYAO hissesi nasıl?", prefer_llm=True)
    assert market.intent == Intent.MARKET
    assert market.use_llm is True
    assert "NASIL" not in (market.reply or "")

    teach_risk = process("Risk tercihim orta", prefer_llm=True)
    assert teach_risk.intent == Intent.MEMORY_TEACH

    # Offline/deterministic path still works without AI.
    local = process_deterministic("Merhaba", memories={"user_name": "Mehmet"})
    assert local.use_llm is False


def test_memory_extract_and_store() -> None:
    found = extract_memories("Benim adım Ayşe")
    assert found and found[0][0] == "user_name"
    assert found[0][1] == "Ayşe"
    assert extract_memories("Adım neydi?") == []

    risk = extract_memories("Risk tercihim orta")
    assert risk and risk[0] == ("risk_profile", "orta", 88)

    watch = extract_memories("Takip ettiğim hisseler: THYAO, ASELS")
    assert watch and watch[0][0] == "watchlist"
    assert "THYAO" in watch[0][1]

    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp) / "test.db")
        store.upsert("user_name", "Ayşe", 95)
        item = store.get("user_name")
        assert item is not None
        assert item.value == "Ayşe"

        teach = process_deterministic("Benim adım Ayşe", memories={"user_name": "Ayşe"})
        assert teach.intent == Intent.MEMORY_TEACH

        recall = process_deterministic("Adım neydi?", memories={"user_name": "Ayşe"})
        assert recall.intent == Intent.MEMORY_QUERY
        assert "Ayşe" in (recall.reply or "")
