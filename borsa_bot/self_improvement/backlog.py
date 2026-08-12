"""Technical improvement backlog — IMPROVEMENT-NNN items."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from self_improvement.audit import Finding, PRIORITY_ORDER, findings_by_priority

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKLOG = ROOT / "self_improvement" / "data" / "backlog.json"


class ItemStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass
class ImprovementItem:
    id: str
    title: str
    priority: str
    severity: str
    category: str
    source_finding_ids: list[str] = field(default_factory=list)
    status: str = ItemStatus.OPEN.value
    acceptance_tests: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ImprovementItem:
        fields = cls.__dataclass_fields__
        return cls(**{k: raw[k] for k in fields if k in raw})


class BacklogStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_BACKLOG
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: list[ImprovementItem] = []
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            self._items = []
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._items = [ImprovementItem.from_dict(x) for x in raw.get("items", [])]

    def save(self) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": [i.to_dict() for i in self._items],
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @property
    def items(self) -> list[ImprovementItem]:
        return list(self._items)

    def next_id(self) -> str:
        n = 1
        existing = {i.id for i in self._items}
        while f"IMPROVEMENT-{n:03d}" in existing:
            n += 1
        return f"IMPROVEMENT-{n:03d}"

    def add(self, item: ImprovementItem) -> ImprovementItem:
        self._items.append(item)
        self.save()
        return item

    def upsert_from_findings(self, findings: list[Finding], *, limit: int = 20) -> list[ImprovementItem]:
        """Create backlog items from audit findings (dedupe by title+path)."""
        created: list[ImprovementItem] = []
        keys = {(i.title, tuple(i.source_finding_ids)) for i in self._items}
        title_paths = {(i.title, i.notes) for i in self._items}
        for f in findings_by_priority(findings)[:limit]:
            key_note = f"{f.path}:{f.line or 0}"
            if (f.title, key_note) in title_paths:
                continue
            item = ImprovementItem(
                id=self.next_id(),
                title=f.title,
                priority=f.suggested_priority if f.suggested_priority in PRIORITY_ORDER else "Maintainability",
                severity=f.severity.value,
                category=f.category,
                source_finding_ids=[f.id],
                acceptance_tests=["tests/test_self_improvement.py"],
                notes=key_note + " — " + f.detail[:180],
            )
            self._items.append(item)
            title_paths.add((f.title, key_note))
            created.append(item)
        if created:
            self.save()
        return created

    def select_next(self) -> ImprovementItem | None:
        """Pick highest priority OPEN item that is auto-safe (not CRITICAL denylist)."""
        open_items = [i for i in self._items if i.status == ItemStatus.OPEN.value]
        if not open_items:
            return None
        pri = {p: idx for idx, p in enumerate(PRIORITY_ORDER)}
        sev = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        open_items.sort(key=lambda i: (pri.get(i.priority, 99), sev.get(i.severity, 9), i.id))
        return open_items[0]

    def update_status(self, item_id: str, status: str, notes: str = "") -> None:
        for i in self._items:
            if i.id == item_id:
                i.status = status
                i.updated_at = datetime.now(timezone.utc).isoformat()
                if notes:
                    i.notes = (i.notes + " | " + notes).strip(" |")
                break
        self.save()
