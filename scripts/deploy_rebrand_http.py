#!/usr/bin/env python3
"""Rebrand dosyalarini HTTP deploy-hook ile yukler."""

from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "php-site"
CREDS = Path(__file__).with_name("ftp-credentials.local.json")

FILES = [
    "config/app.php",
    "app/Services/PhotoWatermarkService.php",
    "app/Services/WatermarkBatchService.php",
    "app/Helpers/helpers.php",
    "app/Helpers/vehicle-models.php",
    "views/partials/create-vehicle-fields.php",
    "admin/watermark-batch.php",
    "views/partials/admin-shell.php",
    "assets/branding/watermark-logo.png",
]


def stamp() -> str:
    tz = timezone(timedelta(hours=3))
    tag = f"deploy-{datetime.now(tz).strftime('%H%M%S')}"
    (SRC / "version.php").write_text(
        "<?php\nreturn [\n"
        f"    'tag' => '{tag}',\n"
        f"    'time' => '{datetime.now(tz).isoformat()}',\n"
        "];\n",
        encoding="utf-8",
    )
    (SRC / "deploy-ping.txt").write_text(tag + "\n", encoding="utf-8")
    FILES.extend(["version.php", "deploy-ping.txt"])
    return tag


def main() -> None:
    c = json.loads(CREDS.read_text(encoding="utf-8"))
    secret = c["deploy_secret"]
    hook = c.get("deploy_hook_url") or (c["site_url"] + "/kurulum.php")
    tag = stamp()
    ok = 0
    print(f"=== HTTP rebrand deploy tag={tag} ===")
    for rel in FILES:
        local = SRC / rel.replace("/", "\\")
        if not local.is_file():
            print(f"  SKIP missing {rel}")
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
            headers={"User-Agent": "BenimBazarDeploy/1.0", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", errors="replace")
        if '"ok":true' in resp.replace(" ", ""):
            print(f"  OK {rel}")
            ok += 1
        else:
            print(f"  FAIL {rel}: {resp[:100]}")
    print(f"Done: {ok}/{len(FILES)}")


if __name__ == "__main__":
    main()
