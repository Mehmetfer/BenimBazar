#!/usr/bin/env python3
import json
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; ChangeXImport/1.0)"}
URL = "https://kpazar.com/ilan/41-2003-mitsubishi-outlander/"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


html = fetch(URL)
print("len", len(html))

for label in [
    "İlan Tarihi",
    "İlan No",
    "Kimden",
    "Yıl",
    "KM",
    "Vites",
    "Yakıt Tipi",
    "Renk",
    "Model",
]:
    m = re.search(rf"{re.escape(label)}[^<{{0,80}}]*?>\s*([^<]+)\s*<", html, re.I | re.S)
    if not m:
        m = re.search(rf"{re.escape(label)}\s*</[^>]+>\s*<[^>]+>\s*([^<]+)", html, re.I | re.S)
    print(label, "=>", m.group(1).strip() if m else None)

photos = sorted(set(re.findall(r"https?://[^\"']+\.(?:webp|jpg|jpeg|png)[^\"']*", html, re.I)))
print("photos", len(photos))
for p in photos[:8]:
    if "kpazar" in p and "logo" not in p.lower():
        print(" ", p[:120])

# seller block
for pat in [
    r"Vis Motors[^<]{0,80}",
    r"Bireysel Satıcı[^<]{0,120}",
    r"Kurumsal[^<]{0,80}",
    r"Galeri[^<]{0,80}",
]:
    m = re.search(pat, html, re.I)
    print(pat, "=>", m.group(0)[:100] if m else None)

links = sorted(set(re.findall(r'href="(/ilan/\d+-[^"]+)"', html)))
print("ilan links on page", len(links))

for test in [
    "https://kpazar.com/ikinci-el-araba/",
    "https://kpazar.com/araba-ilanlari/",
    "https://kpazar.com/ilanlar/",
    "https://kpazar.com/kktc-araba-ilanlari/",
]:
    try:
        h = fetch(test)
        n = len(set(re.findall(r"/ilan/\d+-", h)))
        print(test, "OK", "refs", n)
        pag = re.findall(r'href="([^"]*(?:page|sayfa)[^"]*)"', h, re.I)[:5]
        print("  pag", pag)
    except Exception as e:
        print(test, e)
