#!/usr/bin/env python3
"""Canlidan belirli dosyalari FTP ile yerel php-site'a ceker."""

from __future__ import annotations

import json
import sys
from ftplib import FTP, error_perm
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "php-site"
CREDS = Path(__file__).with_name("ftp-credentials.local.json")

DEFAULT_FILES = [
    "index.php",
    "views/layout.php",
    "views/partials/brand.php",
    "views/partials/home-market.php",
    "views/partials/site-flags.php",
    "views/partials/bottom-nav.php",
    "assets/style.css",
    "assets/theme.js",
    "assets/cx-theme.js",
    "app/Helpers/helpers.php",
    "app/Helpers/region.php",
    "app/Services/ListingService.php",
    "config/app.php",
    "deploy-ping.txt",
    "version.php",
]


def main() -> int:
    files = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_FILES
    c = json.loads(CREDS.read_text(encoding="utf-8"))
    remote_root = str(c.get("remote_dir", "")).strip("/")

    ftp = FTP(c["host"], timeout=90)
    ftp.set_pasv(True)
    ftp.login(c["user"], c["password"])

    ok = 0
    for rel in files:
        rel = rel.replace("\\", "/").lstrip("/")
        parts = rel.split("/")
        try:
            ftp.cwd("/")
            if remote_root:
                for part in remote_root.split("/"):
                    ftp.cwd(part)
            for part in parts[:-1]:
                ftp.cwd(part)
            buf = BytesIO()
            ftp.retrbinary("RETR " + parts[-1], buf.write)
            data = buf.getvalue()
        except error_perm as e:
            print(f"MISS {rel}: {e}")
            continue

        target = SRC / rel.replace("/", "\\")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f"OK {rel} ({len(data)} bytes)")
        ok += 1

    ftp.quit()
    print(f"Done: {ok}/{len(files)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
