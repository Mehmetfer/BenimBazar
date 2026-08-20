#!/usr/bin/env python3
"""Scan live listings for populated market-compare section."""
import re
import urllib.request

UA = {"User-Agent": "BenimBazarCheck/1.0"}
BASE = "http://changex.mehmetfer.com.tr"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def has_market_data(html: str) -> bool:
    if "market-compare--empty" in html:
        return False
    if "market-compare__verdict" not in html:
        return False
    # Must have sample count or price stats, not just shell
    return bool(
        re.search(r"market-compare__stat-value|market-compare__samples|örnek ilan", html, re.I)
    )


def main() -> None:
    xml = fetch(f"{BASE}/sitemap-listings.php")
    ids = [int(m) for m in re.findall(r"listing\.php\?id=(\d+)", xml)]
    filled: list[int] = []
    empty = 0
    no_section = 0

    for lid in ids:
        try:
            html = fetch(f"{BASE}/listing.php?id={lid}")
        except Exception as e:
            print(f"skip {lid}: {e}")
            continue

        if "market-compare" not in html:
            no_section += 1
            continue
        if has_market_data(html):
            filled.append(lid)
            print(f"FILLED: {lid} -> {BASE}/listing.php?id={lid}#piyasa")
        else:
            empty += 1

    print("---")
    print(f"total_ids={len(ids)} filled={len(filled)} empty={empty} no_section={no_section}")
    if filled:
        print("examples:", ", ".join(str(i) for i in filled[:10]))


if __name__ == "__main__":
    main()
