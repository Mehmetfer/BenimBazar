#!/usr/bin/env python3
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; ChangeXImport/1.0)"}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


base = "https://kibrisarabaal.com/arac-kibris-2-el-araba/"
html = fetch(base)
ilans = sorted(set(re.findall(r"/ilan/(\d+)-[^\"']+", html)))
print("page1 ids", len(ilans), "min", min(map(int, ilans)) if ilans else None, "max", max(map(int, ilans)) if ilans else None)

pages = sorted(set(re.findall(r'href="([^"]*arac-kibris[^"]*sayfa[^"]*)"', html, re.I)))
print("pagination links", pages[:20])

# try common pagination patterns
for p in [2, 3, 10, 50]:
    for pat in [
        f"https://kibrisarabaal.com/arac-kibris-2-el-araba/sayfa/{p}/",
        f"https://kibrisarabaal.com/arac-kibris-2-el-araba/?page={p}",
        f"https://kibrisarabaal.com/arac-kibris-2-el-araba/page/{p}/",
    ]:
        try:
            h = fetch(pat)
            ids = set(re.findall(r"/ilan/(\d+)-", h))
            if ids:
                print("OK", pat, "ids", len(ids))
        except Exception as e:
            pass

# sort links
sorts = re.findall(r'href="([^"]+)"[^>]*>(?:En Eski|En Yeni|Tarih|date)[^<]*', html, re.I)
print("sort links", sorts)

all_links = [l for l in re.findall(r'href="([^"]+)"', html) if "sort" in l.lower() or "order" in l.lower() or "tarih" in l.lower()]
print("order-ish", all_links[:15])
