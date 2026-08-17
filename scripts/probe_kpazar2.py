#!/usr/bin/env python3
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; ChangeXImport/1.0)"}
html = urllib.request.urlopen(
    urllib.request.Request(
        "https://kpazar.com/ilan/41-2003-mitsubishi-outlander/", headers=UA
    ),
    timeout=45,
).read().decode("utf-8", "replace")

# seller card area
for pat in [
    r'class="[^"]*seller[^"]*"[^>]*>([\s\S]{0,800})',
    r'Vis Motors Trading Ltd',
    r'class="[^"]*owner[^"]*"',
    r'Kimden[^<]{0,200}',
    r'£[\d.,]+',
    r'uploads/2026/07/[^"\']+',
]:
    ms = re.findall(pat, html, re.I)
    print("===", pat[:40], len(ms))
    for m in ms[:2]:
        s = m if isinstance(m, str) else str(m)
        print(s[:200].replace("\n", " "))

# list page
h2 = urllib.request.urlopen(
    urllib.request.Request("https://kpazar.com/kktc-araba-ilanlari/", headers=UA),
    timeout=45,
).read().decode("utf-8", "replace")
urls = sorted(set(re.findall(r'href="(https://kpazar\.com/ilan/\d+-[^"]+)"', h2)))
print("list urls", len(urls), urls[:3])
pages = re.findall(r'href="(\?sayfa=\d+|\?page=\d+|/kktc-araba-ilanlari/\?sayfa=\d+)"', h2)
print("pages", pages[:5])

# another listing with individual seller
html2 = urllib.request.urlopen(
    urllib.request.Request("https://kpazar.com/kktc-araba-ilanlari/", headers=UA),
    timeout=45,
).read().decode("utf-8", "replace")
first = re.search(r'href="(https://kpazar\.com/ilan/\d+-[^"]+)"', html2)
if first:
    u = first.group(1)
    h = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=45).read().decode("utf-8", "replace")
    sm = re.search(r'class="[^"]*seller-name[^"]*"[^>]*>([^<]+)', h, re.I)
    print("first listing", u)
    print("seller-name class", sm.group(1) if sm else "none")
    # try h3/h4 near Bireysel
    bm = re.search(r'>\s*([A-Za-zÇĞİÖŞÜçğıöşü][^<]{2,60})\s*</[^>]+>\s*[^<]{0,200}Bireysel Sat', h, re.I | re.S)
    print("before bireysel", bm.group(1).strip() if bm else "none")
