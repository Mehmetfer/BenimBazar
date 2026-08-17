#!/usr/bin/env python3
"""Canli deploy: once FTP, basarisizsa HTTP deploy-hook (docroot uyumsuzlugunda)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from ftplib import FTP, error_perm
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "php-site"
CREDS = Path(__file__).with_name("ftp-credentials.local.json")
CACHE = Path(__file__).with_name(".deploy-cache.json")

SKIP_UPLOAD = {
    "config/database.php",
    "config/database.local.php",
    "config/google.local.php",
    "config/deploy.local.php",
    "config/setup.local.php",
}

SITE_URL = "http://changex.mehmetfer.com.tr"


def load_creds() -> dict:
    if not CREDS.exists():
        print(f"Eksik: {CREDS}", file=sys.stderr)
        sys.exit(1)
    return json.loads(CREDS.read_text(encoding="utf-8"))


def save_cache(mode: str, detail: str, tag: str) -> None:
    CACHE.write_text(
        json.dumps({"mode": mode, "detail": detail, "last_tag": tag, "at": datetime.now().isoformat()}, indent=2),
        encoding="utf-8",
    )


def cwd_remote(ftp: FTP, remote_dir: str) -> None:
    ftp.cwd("/")
    rd = remote_dir.strip("/")
    if not rd:
        return
    for part in rd.split("/"):
        try:
            ftp.cwd(part)
        except error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def live_deploy_tag(site_url: str = SITE_URL) -> str | None:
    try:
        req = urllib.request.Request(
            site_url + "/deploy-ping.txt",
            headers={"User-Agent": "ChangeXDeploy/1.0", "Cache-Control": "no-cache"},
        )
        body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="replace").strip()
        if body and len(body) < 80 and not body.startswith("<"):
            return body
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    try:
        req = urllib.request.Request(
            site_url + "/index.php",
            headers={"User-Agent": "ChangeXDeploy/1.0", "Cache-Control": "no-cache"},
        )
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="replace")
        m = re.search(r"FTP deploy:\s*([^\s·<]+)", html)
        return m.group(1).strip() if m else None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def stamp_deploy_marker() -> str:
    tz = timezone(timedelta(hours=3))
    now = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S%z")
    now = now[:-2] + ":" + now[-2:]
    tag = f"deploy-{datetime.now(tz).strftime('%H%M%S')}"
    (SRC / "version.php").write_text(
        "<?php\nreturn [\n"
        f"    'tag' => '{tag}',\n"
        f"    'time' => '{now}',\n"
        "];\n",
        encoding="utf-8",
    )
    (SRC / "deploy-ping.txt").write_text(tag + "\n", encoding="utf-8")
    return tag


def iter_files() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for path in sorted(SRC.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SRC).as_posix()
        if rel in SKIP_UPLOAD:
            continue
        out.append((rel, path))
    return out


def deploy_ftp(c: dict, files: list[tuple[str, Path]]) -> str:
    remote = str(c.get("remote_dir", ""))
    ftp = FTP(c["host"], timeout=180)
    ftp.set_pasv(True)
    ftp.login(c["user"], c["password"])
    print(f"FTP: {c['user']} @ {c['host']} -> {remote or '/'}")
    for rel, local in files:
        parts = rel.split("/")
        ftp.cwd("/")
        cwd_remote(ftp, remote)
        for part in parts[:-1]:
            try:
                ftp.cwd(part)
            except error_perm:
                ftp.mkd(part)
                ftp.cwd(part)
        with local.open("rb") as f:
            ftp.storbinary(f"STOR {parts[-1]}", f)
        print(f"  FTP OK {rel}")
    ftp.quit()
    return remote


def deploy_http(secret: str, hook_url: str, files: list[tuple[str, Path]]) -> int:
    ok = 0
    for rel, local in files:
        payload = {
            "secret": secret,
            "islem": "deployrecv",
            "path": rel,
            "content_b64": base64.b64encode(local.read_bytes()).decode("ascii"),
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            hook_url,
            data=data,
            headers={"User-Agent": "ChangeXDeploy/1.0", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")
            if '"ok":true' in resp.replace(" ", ""):
                print(f"  HTTP OK {rel}")
                ok += 1
            else:
                print(f"  HTTP FAIL {rel}: {resp[:120]}", file=sys.stderr)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:120]
            print(f"  HTTP FAIL {rel}: {e.code} {body}", file=sys.stderr)
            if e.code == 503 and "deploy.local" in body:
                print("\nTEK SEFERLIK: cPanel'de config/deploy.local.php olusturun (deploy.local.php.example)", file=sys.stderr)
                return ok
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  HTTP FAIL {rel}: {e}", file=sys.stderr)
    return ok


def main() -> None:
    if not SRC.is_dir():
        print("php-site yok", file=sys.stderr)
        sys.exit(1)

    tag = stamp_deploy_marker()
    c = load_creds()
    files = iter_files()
    site_url = (c.get("site_url") or SITE_URL).rstrip("/")

    print(f"=== DEPLOY tag={tag} ({len(files)} dosya) ===")

    # 1) FTP
    try:
        deploy_ftp(c, files)
    except Exception as e:
        print(f"FTP hatasi: {e}", file=sys.stderr)

    time.sleep(2)
    if live_deploy_tag(site_url) == tag:
        save_cache("ftp", c.get("remote_dir", ""), tag)
        print(f"CANLI OK (FTP) — {site_url}/index.php")
        return

    print("FTP canliya yansimadi — HTTP deploy-hook deneniyor...")

    secret = c.get("deploy_secret", "")
    hook = c.get("deploy_hook_url") or (site_url + "/kurulum.php")
    if not secret:
        print("HTTP atlandi: ftp-credentials.local.json icinde deploy_secret yok", file=sys.stderr)
    else:
        n = deploy_http(secret, hook, files)
        time.sleep(2)
        if live_deploy_tag(site_url) == tag:
            save_cache("http", hook, tag)
            print(f"CANLI OK (HTTP) — {site_url}/index.php")
            return
        print(f"HTTP yuklendi: {n}/{len(files)} dosya", file=sys.stderr)

    print("\n=== COZUM (tek seferlik cPanel) ===", file=sys.stderr)
    print("FTP klasoru != site klasoru. Asagidakilerden BIRINI yapin:", file=sys.stderr)
    print("A) Alt Alan Adlari -> changex.mehmetfer.com.tr -> Document Root", file=sys.stderr)
    print("   FTP Hesaplari -> mehmetfer@changex.mehmetfer.com.tr -> AYNI dizin", file=sys.stderr)
    print("B) config/deploy.local.php + deploy-hook.php (ornek dosyalarda)", file=sys.stderr)
    print("   ftp-credentials.local.json -> deploy_secret ayni anahtar", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
