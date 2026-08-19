#!/usr/bin/env python3
"""kka-queue JSON + ext-import fotograflarini canliya HTTP deploy-hook ile yukler."""

from __future__ import annotations

import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "php-site"
CREDS = Path(__file__).with_name("ftp-credentials.local.json")
QUEUE = ROOT / "storage" / "kka-queue"
PHOTOS = ROOT / "uploads" / "ext-import"


def upload(rel: str, local: Path, hook: str, secret: str) -> bool:
    if not local.is_file():
        print(f"MISSING {rel}")
        return False
    payload = {
        "secret": secret,
        "islem": "deployrecv",
        "path": rel,
        "content_b64": base64.b64encode(local.read_bytes()).decode("ascii"),
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        hook,
        data=data,
        headers={
            "User-Agent": "KkaQueueUpload/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"FAIL {rel}: {e}")
        return False
    good = '"ok":true' in resp.replace(" ", "")
    print(f"{rel}: {'OK' if good else resp[:80]}")
    return good


def main() -> int:
    c = json.loads(CREDS.read_text(encoding="utf-8"))
    hook = c.get("deploy_hook_url") or (c.get("site_url", "").rstrip("/") + "/kurulum.php")
    secret = c["deploy_secret"]

    files: list[tuple[str, Path]] = []
    for fp in sorted(QUEUE.glob("*.json")):
        files.append((f"storage/kka-queue/{fp.name}", fp))

    photo_names: set[str] = set()
    for fp in QUEUE.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for name in data.get("local_photos") or []:
            if name:
                photo_names.add(str(name))

    for name in sorted(photo_names):
        local = PHOTOS / name
        files.append((f"uploads/ext-import/{name}", local))

    ok = sum(int(upload(rel, local, hook, secret)) for rel, local in files)
    print(f"uploaded {ok}/{len(files)}")
    return 0 if ok == len(files) else 2


if __name__ == "__main__":
    raise SystemExit(main())
