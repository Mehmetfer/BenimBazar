#!/usr/bin/env python3
"""Canlidan dosya listesini HTTP deployget ile ceker."""

from __future__ import annotations

import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "php-site"
CREDS = Path(__file__).with_name("ftp-credentials.local.json")
LIST = Path(__file__).with_name(".pull-filelist.txt")


def pull_one(secret: str, hook: str, rel: str) -> bytes | None:
    payload = urllib.parse.urlencode(
        {"secret": secret, "islem": "deployget", "path": rel}
    ).encode("utf-8")
    req = urllib.request.Request(
        hook,
        data=payload,
        headers={
            "User-Agent": "BenimBazarPull/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        raw = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"FAIL {rel}: {e}")
        return None
    if '"ok":true' not in raw.replace(" ", ""):
        print(f"MISS {rel}: {raw[:120]}")
        return None
    data = json.loads(raw)
    return base64.b64decode(data["content_b64"])


def main() -> int:
    if LIST.is_file():
        files = [ln.strip() for ln in LIST.read_text(encoding="utf-8").splitlines() if ln.strip()]
    elif len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        print("No file list", file=sys.stderr)
        return 1

    c = json.loads(CREDS.read_text(encoding="utf-8"))
    secret = c["deploy_secret"]
    hook = c.get("deploy_hook_url") or (c["site_url"].rstrip("/") + "/kurulum.php")

    ok = miss = 0
    for rel in files:
        content = pull_one(secret, hook, rel)
        if content is None:
            miss += 1
            continue
        target = SRC / rel.replace("/", "\\")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        ok += 1
        if ok % 25 == 0:
            print(f"... {ok} pulled")

    print(f"Done: {ok} OK, {miss} miss, {len(files)} total")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
