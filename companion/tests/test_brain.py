from __future__ import annotations

import tempfile
from pathlib import Path

from companion.app.brain import Intent, process_deterministic, try_math
from companion.app.memory import MemoryStore, extract_memories


def test_math() -> None:
    assert try_math("12 + 5 kaç?") == "17"
    assert try_math("8 x 3") == "24"


def test_greeting_and_empathy() -> None:
    greet = process_deterministic("Merhaba", memories={"user_name": "Mehmet"})
    assert greet.intent == Intent.GREETING
    assert "Mehmet" in (greet.reply or "")

    empathy = process_deterministic("Bugün çok yalnızım")
    assert empathy.intent == Intent.EMPATHY
    assert empathy.use_llm is False


def test_memory_extract_and_store() -> None:
    found = extract_memories("Benim adım Ayşe")
    assert found and found[0][0] == "user_name"
    assert found[0][1] == "Ayşe"
    assert extract_memories("Adım neydi?") == []

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
