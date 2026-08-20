#!/usr/bin/env python3
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; ChangeXImport/1.0)"}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main() -> None:
    url = "https://kibrisarabaal.com/ilan/1195-2010-model-otomatik-mini-cooper-a1e60d/"
    html = fetch(url)
    print("len", len(html))

    imgs = re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*', html, re.I)
    print("imgs", len(imgs))
    for u in sorted(set(imgs))[:12]:
        print(" ", u[:140])

    for pat in [
        r"İlan Tarihi:\s*([^<\n]+)",
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'property="og:image"\s+content="([^"]+)"',
    ]:
        m = re.search(pat, html)
        print(pat, "=>", m.group(1).strip() if m else None)

    links = re.findall(r'href="(https://kibrisarabaal\.com/ilan/[^"]+)"', html)
    print("ilan links on page", len(set(links)))

    for test in [
        "https://kibrisarabaal.com/ilanlar/",
        "https://kibrisarabaal.com/ilanlar/?sort=date_asc",
        "https://kibrisarabaal.com/ilanlar/?sort=oldest",
        "https://kibrisarabaal.com/ilanlar/sayfa/1/",
        "https://kibrisarabaal.com/wp-json/wp/v2/posts",
    ]:
        try:
            h = fetch(test)
            ilans = re.findall(r"/ilan/\d+-", h)
            print(test, "status ok", "ilan refs", len(set(ilans)))
        except Exception as e:
            print(test, "ERR", e)


if __name__ == "__main__":
    main()
