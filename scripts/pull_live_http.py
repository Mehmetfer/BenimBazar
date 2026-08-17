#!/usr/bin/env python3
"""Canlidan HTTP deployget ile dosya ceker (kurulum.php deployget gerekir)."""

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

DEFAULT = [
    "index.php",
    "kurulum.php",
    "views/layout.php",
    "views/partials/brand.php",
    "views/partials/home-market.php",
    "views/partials/site-flags.php",
    "views/partials/site-legal-footer.php",
    "views/partials/bottom-nav.php",
    "assets/style.css",
    "assets/theme-toggle.js",
    "app/Helpers/helpers.php",
    "app/Helpers/region.php",
    "app/Services/ListingService.php",
    "config/app.php",
    "kullanim-kosullari.php",
    "ekspertiz-kosullari.php",
    "listing.php",
    "deploy-ping.txt",
    "version.php",
]


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
        print(f"MISS {rel}: {raw[:100]}")
        return None
    data = json.loads(raw)
    return base64.b64decode(data["content_b64"])


def main() -> int:
    files = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT
    c = json.loads(CREDS.read_text(encoding="utf-8"))
    secret = c["deploy_secret"]
    hook = c.get("deploy_hook_url") or (c["site_url"].rstrip("/") + "/kurulum.php")
    ok = 0
    for rel in files:
        content = pull_one(secret, hook, rel)
        if content is None:
            continue
        target = SRC / rel.replace("/", "\\")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        print(f"OK {rel} ({len(content)} bytes)")
        ok += 1
    print(f"Done: {ok}/{len(files)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
