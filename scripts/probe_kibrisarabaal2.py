#!/usr/bin/env python3
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; ChangeXImport/1.0)"}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


html = fetch("https://kibrisarabaal.com/")
links = sorted(set(re.findall(r'href="([^"]+)"', html)))
for l in links:
    if "ilan" in l.lower() or "araba" in l.lower() or "galeri" in l.lower() or "page" in l.lower():
        print(l)

print("--- ilan urls ---")
ilans = sorted(set(re.findall(r"https://kibrisarabaal\.com/ilan/\d+-[^\"']+", html)))
print("count", len(ilans))
for u in ilans[:5]:
    print(u)

# search listing date in detail html raw
html2 = fetch("https://kibrisarabaal.com/ilan/1195-2010-model-otomatik-mini-cooper-a1e60d/")
for kw in ["İlan Tarihi", "ilan-tarihi", "listing-date", "published", "Temmuz", "2026"]:
    idx = html2.find(kw)
    print(kw, idx)
    if idx >= 0:
        print(html2[idx : idx + 120].replace("\n", " "))

# gallery links
gals = sorted(set(re.findall(r'href="(https://kibrisarabaal\.com/galeri/[^"]+)"', html)))
print("galleries homepage", len(gals))
