#!/usr/bin/env python3
"""Canlidan tum php-site kod dosyalarini FTP ile yerel php-site'a ceker."""

from __future__ import annotations

import json
import sys
from ftplib import FTP, error_perm
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "php-site"
CREDS = Path(__file__).with_name("ftp-credentials.local.json")

SKIP_DIRS = {
    "uploads",
    "storage/sessions",
    "storage/logs",
    "storage/kka-queue",
    "storage/kpazar-queue",
    ".git",
}

SKIP_FILES = {
    "config/database.php",
    "config/database.local.php",
    "config/google.local.php",
    "config/setup.local.php",
    "config/deploy.local.php",
    "config/sms.local.php",
    "config/whatsapp.local.php",
}


def should_skip(rel: str) -> bool:
    rel = rel.replace("\\", "/").lstrip("/")
    for d in SKIP_DIRS:
        if rel == d or rel.startswith(d + "/"):
            return True
    return rel in SKIP_FILES


def cwd_remote(ftp: FTP, remote_root: str) -> None:
    ftp.cwd("/")
    if not remote_root:
        return
    for part in remote_root.strip("/").split("/"):
        if part:
            ftp.cwd(part)


def list_recursive(ftp: FTP, prefix: str = "") -> list[str]:
    out: list[str] = []
    try:
        entries: list[tuple[str, ...]] = []
        ftp.retrlines("LIST", lambda line: entries.append(tuple(line.split(maxsplit=8))))
    except error_perm:
        return out

    for parts in entries:
        if len(parts) < 9:
            continue
        name = parts[-1]
        if name in (".", ".."):
            continue
        is_dir = parts[0].startswith("d")
        rel = f"{prefix}/{name}".lstrip("/")
        if should_skip(rel):
            continue
        if is_dir:
            ftp.cwd(name)
            out.extend(list_recursive(ftp, rel))
            ftp.cwd("..")
        else:
            out.append(rel)
    return out


def download_file(ftp: FTP, rel: str, remote_root: str) -> bool:
    parts = rel.split("/")
    try:
        cwd_remote(ftp, remote_root)
        for part in parts[:-1]:
            ftp.cwd(part)
        buf = BytesIO()
        ftp.retrbinary("RETR " + parts[-1], buf.write)
        data = buf.getvalue()
    except error_perm as e:
        print(f"MISS {rel}: {e}")
        return False

    target = SRC / rel.replace("/", "\\")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print(f"OK {rel} ({len(data)} bytes)")
    return True


def main() -> int:
    if not CREDS.is_file():
        print("Missing ftp-credentials.local.json", file=sys.stderr)
        return 1

    c = json.loads(CREDS.read_text(encoding="utf-8"))
    remote_root = str(c.get("remote_dir", "")).strip("/")

    ftp = FTP(c["host"], timeout=120)
    ftp.set_pasv(True)
    ftp.login(c["user"], c["password"])
    cwd_remote(ftp, remote_root)

    print(f"Listing remote: /{remote_root or ''}")
    files = sorted(set(list_recursive(ftp)))
    print(f"Found {len(files)} files to pull")

    ok = 0
    for rel in files:
        if download_file(ftp, rel, remote_root):
            ok += 1

    ftp.quit()
    print(f"Done: {ok}/{len(files)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
