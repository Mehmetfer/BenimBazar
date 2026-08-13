"""Configurable contact-info detector (phone / email / social) with confidence."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum


class ContactPolicy(str, Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"
    ALLOW = "ALLOW"


def contact_policy() -> ContactPolicy:
    raw = (os.environ.get("CHANGEX_CONTACT_POLICY") or "WARN").strip().upper()
    try:
        return ContactPolicy(raw)
    except ValueError:
        return ContactPolicy.WARN


@dataclass
class ContactHit:
    kind: str
    match: str
    confidence: float

    def to_dict(self) -> dict:
        return {"kind": self.kind, "match": self.match, "confidence": self.confidence}


_PHONE = re.compile(
    r"(?<!\d)(?:\+?90|0)?[\s\-.]*(?:5\d{2})[\s\-.]*\d{3}[\s\-.]*\d{2}[\s\-.]*\d{2}(?!\d)"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SOCIAL = re.compile(
    r"(?i)\b(?:instagram|insta|twitter|x\.com|telegram|whatsapp|wa\.me|facebook|fb\.com)\b"
    r"|@[A-Za-z0-9_]{3,}"
)


def detect_contact_info(text: str) -> list[ContactHit]:
    hits: list[ContactHit] = []
    body = text or ""
    for m in _PHONE.finditer(body):
        hits.append(ContactHit("phone", m.group(0), 0.85))
    for m in _EMAIL.finditer(body):
        hits.append(ContactHit("email", m.group(0), 0.9))
    for m in _SOCIAL.finditer(body):
        conf = 0.75 if m.group(0).startswith("@") else 0.8
        hits.append(ContactHit("social_or_external", m.group(0), conf))
    return hits
