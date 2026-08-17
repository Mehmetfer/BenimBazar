#!/usr/bin/env python3
"""Belirli dosyalari HTTP deploy-hook ile yukler."""

from __future__ import annotations

import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "php-site"
CREDS = Path(__file__).with_name("ftp-credentials.local.json")


def main() -> int:
    if len(sys.argv) < 2:
        print("Kullanim: deploy_files.py path1 path2 ...", file=sys.stderr)
        return 1

    c = json.loads(CREDS.read_text(encoding="utf-8"))
    hook = c["deploy_hook_url"]
    secret = c["deploy_secret"]
    ok = 0
    for rel in sys.argv[1:]:
        local = ROOT / rel.replace("/", "\\")
        if not local.is_file():
            print(f"MISSING {rel}")
            continue
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
                "User-Agent": "ChangeXDeploy/1.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", errors="replace")
        good = '"ok":true' in resp.replace(" ", "")
        ok += int(good)
        print(f"{rel}: {'OK' if good else resp[:100]}")
    total = len(sys.argv) - 1
    print(f"uploaded {ok}/{total}")
    return 0 if ok == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
