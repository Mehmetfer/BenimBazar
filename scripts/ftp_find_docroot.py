#!/usr/bin/env python3
"""Canli docroot icin dogru FTP yolunu bul."""
import json
import time
import urllib.request
from ftplib import FTP
from io import BytesIO
from pathlib import Path

CREDS = Path(__file__).with_name("ftp-credentials.local.json")
SITE = "http://changex.mehmetfer.com.tr/deploy-ping.txt"

ACCOUNTS = [
    ("mehmetfer@changex.mehmetfer.com.tr", json.loads(CREDS.read_text())["password"]),
    ("mehmetfer@mehmetfer.com.tr", json.loads(CREDS.read_text())["password"]),
]

PATHS = [
    "",
    "changex.mehmetfer.com.tr",
    "public_html/changex.mehmetfer.com.tr",
    "../changex.mehmetfer.com.tr",
    "domains/changex.mehmetfer.com.tr/public_html",
]


def live_ping() -> str:
    try:
        return urllib.request.urlopen(SITE, timeout=15).read().decode().strip()[:40]
    except Exception:
        return ""


def try_upload(user: str, pw: str, base: str, marker: str) -> bool:
    try:
        ftp = FTP("ftp.mehmetfer.com.tr", timeout=30)
        ftp.set_pasv(True)
        ftp.login(user, pw)
        ftp.cwd("/")
        for part in base.split("/"):
            if part in ("", ".") :
                continue
            if part == "..":
                ftp.cwd("..")
            else:
                ftp.cwd(part)
        ftp.storbinary("STOR deploy-ping.txt", BytesIO(marker.encode()))
        ftp.quit()
        time.sleep(2)
        got = live_ping()
        return got == marker
    except Exception as e:
        print(f"  FAIL {user} @ {base!r}: {e}")
        return False


print("Canli once:", live_ping()[:30])
for user, pw in ACCOUNTS:
    for base in PATHS:
        marker = f"path-{user.split('@')[0]}-{base.replace('/','_') or 'root'}"[:40]
        print(f"Deneme {user} path={base!r} marker={marker}")
        if try_upload(user, pw, base, marker):
            print(">>> BULUNDU <<<", user, base)
            raise SystemExit(0)
print("Hicbir yol canliya yazmadi.")
