#!/usr/bin/env python3
import json
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; ChangeXImport/1.0)"}
URL = "https://kibrisarabaal.com/ilan/1195-2010-model-otomatik-mini-cooper-a1e60d/"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


html = fetch(URL)

# specs block
specs = {}
for label in [
    "Yıl",
    "Kilometre",
    "Vites Tipi",
    "Yakıt Türü",
    "Kasa Tipi",
    "Motor Hacmi",
    "Renk",
    "Araç Durumu",
    "Direksiyon Tipi",
    "İlan Tarihi",
    "İlan Numarası",
]:
    m = re.search(
        rf"{re.escape(label)}:\s*</span>\s*<span[^>]*>\s*([^<]+)\s*</span>",
        html,
        re.I | re.S,
    )
    if not m:
        m = re.search(rf"{re.escape(label)}[^<]*</[^>]+>\s*<[^>]+>\s*([^<]+)", html, re.I | re.S)
    specs[label] = m.group(1).strip() if m else None

print(json.dumps(specs, ensure_ascii=False, indent=2))

# price
pm = re.search(r"([\d.,]+)\s*£", html)
print("price_gbp", pm.group(1) if pm else None)
pm2 = re.search(r"([\d.,]+)\s*₺", html)
print("price_try", pm2.group(1) if pm2 else None)

# photos - listing uploads only
photos = sorted(
    set(
        re.findall(
            r"https://kibrisarabaal\.com/uploads/listings/\d+/img_[^\"']+\.(?:webp|jpg|jpeg|png)",
            html,
            re.I,
        )
    )
)
print("photos", len(photos))
for p in photos:
    print(" ", p)

# seller
for pat in [
    r"Kurumsal Üye",
    r"Kurumsal Galeri",
    r'galeri/([a-z0-9-]+)/',
    r"Galeri Hakkında",
]:
    print(pat, bool(re.search(pat, html, re.I)))

m = re.search(r'href="https://kibrisarabaal\.com/galeri/([^"/]+)/"', html)
print("gallery slug", m.group(1) if m else None)

# description - rough
dm = re.search(r'id="description"[^>]*>(.*?)</div>', html, re.I | re.S)
if not dm:
    dm = re.search(r'class="[^"]*description[^"]*"[^>]*>(.*?)</div>', html, re.I | re.S)
print("desc len", len(re.sub(r"<[^>]+>", " ", dm.group(1))) if dm else 0)

# title
tm = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
print("title", tm.group(1).strip() if tm else None)

# location
lm = re.search(r"Lefkoşa[^<]{0,80}", html)
print("loc snippet", lm.group(0)[:80] if lm else None)
