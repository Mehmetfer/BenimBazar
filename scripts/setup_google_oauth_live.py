#!/usr/bin/env python3
"""Canli sunucuda kurulum.php ile google.local.php yazar."""
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cfg_path = ROOT / "php-site" / "config" / "google.local.php"
if not cfg_path.is_file():
    print("HATA: google.local.php bulunamadi:", cfg_path)
    sys.exit(1)

cfg = cfg_path.read_text(encoding="utf-8")
cid_m = re.search(r"'client_id'\s*=>\s*'([^']+)'", cfg)
sec_m = re.search(r"'client_secret'\s*=>\s*'([^']+)'", cfg)
if not cid_m or not sec_m:
    print("HATA: client_id veya client_secret parse edilemedi")
    sys.exit(1)

data = urllib.parse.urlencode(
    {
        "anahtar": "CHANGEX2026",
        "islem": "googleconfig",
        "client_id": cid_m.group(1),
        "client_secret": sec_m.group(1),
    }
).encode()

req = urllib.request.Request(
    "http://changex.mehmetfer.com.tr/kurulum.php",
    data=data,
    method="POST",
)
html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")
msgs = re.findall(r'<div class="msg">([^<]+)</div>', html)
if not msgs:
    print("Yanit mesaji bulunamadi (ilk 500 karakter):")
    print(html[:500])
    sys.exit(1)

for m in msgs:
    print(m)

if any("AKTIF" in m for m in msgs):
    sys.exit(0)
sys.exit(2)
