#!/usr/bin/env python3
"""
kpazar.com -> ChangeX import kuyrugu.
1 Haziran 2026 sonrasi, ilan tarihine gore eskiden yeniye.

Kullanim:
  python scripts/kpazar_build_queue.py
  python scripts/kpazar_build_queue.py --limit 5
  python scripts/kpazar_build_queue.py --download-only
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT / "php-site" / "storage" / "kpazar-queue"
PHOTO_DIR = ROOT / "php-site" / "uploads" / "ext-import"
META_FILE = ROOT / "scripts" / ".kpazar-queue-meta.json"

BASE = "https://kpazar.com"
ARCHIVE = f"{BASE}/kktc-araba-ilanlari/"
SOURCE = "kpazar.com"
CUTOFF = datetime(2026, 6, 1)
DATE_FROM = CUTOFF
DATE_TO: datetime | None = None
UA = "Mozilla/5.0 (compatible; ChangeXImport/1.0)"

TR_MONTHS = {
    "ocak": 1, "subat": 2, "şubat": 2, "mart": 3, "nisan": 4,
    "mayis": 5, "mayıs": 5, "haziran": 6, "temmuz": 7,
    "agustos": 8, "ağustos": 8, "eylul": 9, "eylül": 9,
    "ekim": 10, "kasim": 11, "kasım": 11, "aralik": 12, "aralık": 12,
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def parse_tr_date(text: str) -> datetime | None:
    text = html_lib.unescape(text.strip().lower())
    m = re.search(r"(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})", text)
    if not m:
        return None
    month = TR_MONTHS.get(m.group(2))
    if not month:
        return None
    return datetime(int(m.group(3)), month, int(m.group(1)))


def parse_iso_date(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return None


def in_date_range(listed_dt: datetime) -> bool:
    if listed_dt < DATE_FROM:
        return False
    if DATE_TO is not None and listed_dt > DATE_TO:
        return False
    return True


def parse_amount(raw: str) -> float:
    s = raw.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        return float(s.replace(".", ""))
    if "," in s and "." in s:
        return float(s.replace(".", "").replace(",", "."))
    if "," in s:
        return float(s.replace(",", "."))
    return float(s)


def parse_price(html: str) -> dict | None:
    matches = re.findall(r"£([\d.,]+)", html)
    for raw in matches:
        raw = raw.strip()
        if not raw:
            continue
        if re.fullmatch(r"\d{1,3}(,\d{3})+", raw):
            amount = float(raw.replace(",", ""))
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
            amount = float(raw.replace(".", ""))
        else:
            amount = parse_amount(raw)
        if amount >= 100:
            return {"currency": "GBP", "amount": amount}
    if matches:
        raw = matches[0]
        if re.fullmatch(r"\d{1,3}(,\d{3})+", raw):
            return {"currency": "GBP", "amount": float(raw.replace(",", ""))}
        return {"currency": "GBP", "amount": parse_amount(raw)}
    m2 = re.search(r"([\d.,]+)\s*₺", html)
    if m2 and "£" not in html[:12000]:
        return {"currency": "TRY", "amount": parse_amount(m2.group(1))}
    return None


def spec_value(html: str, label: str) -> str | None:
    patterns = [
        rf">{re.escape(label)}\s*</div>\s*<div[^>]*>\s*([^<]+)\s*<",
        rf"{re.escape(label)}\s*</[^>]+>\s*<[^>]+>\s*([^<]+)",
        rf"{re.escape(label)}:\s*</span>\s*<span[^>]*>\s*([^<]+)\s*</span>",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I | re.S)
        if m:
            return html_lib.unescape(re.sub(r"\s+", " ", m.group(1)).strip())
    return None


def crawl_listing_urls() -> list[str]:
    seen: set[str] = set()
    page = 1
    while page <= 100:
        url = ARCHIVE if page == 1 else f"{ARCHIVE}?sayfa={page}"
        try:
            html = fetch(url)
        except urllib.error.HTTPError:
            break
        found = re.findall(r'href="(https://kpazar\.com/ilan/\d+-[^"]+)"', html)
        if not found:
            found = re.findall(r'href="(/ilan/\d+-[^"]+)"', html)
            found = [BASE + p if p.startswith("/") else p for p in found]
        if not found:
            break
        new = 0
        for full in found:
            if full not in seen:
                seen.add(full)
                new += 1
        if new == 0:
            break
        page += 1
        time.sleep(0.25)
    return sorted(seen, key=lambda u: int(re.search(r"/ilan/(\d+)-", u).group(1)))


def parse_title_parts(title: str) -> tuple[str, str, str]:
    title = re.sub(r"\s+", " ", title.strip())
    m = re.match(r"^(?:(\d{4})\s+Model\s+)?(?:(Otomatik|Manuel)\s+)?(.+)$", title, re.I)
    if not m:
        return "", "", title
    year, _, rest = m.group(1) or "", m.group(2) or "", m.group(3).strip()
    # marka model: son kelime model olabilir
    tokens = rest.split()
    if len(tokens) >= 2:
        make = tokens[0]
        model = " ".join(tokens[1:])
    else:
        make, model = rest, ""
    return year, make, model


def parse_listing(url: str) -> dict | None:
    html = fetch(url)
    m = re.search(r"/ilan/(\d+)-", url)
    if not m:
        return None
    source_id = int(m.group(1))

    listed_at = spec_value(html, "İlan Tarihi") or spec_value(html, "Ilan Tarihi")
    listed_dt = parse_tr_date(listed_at or "")
    if listed_dt is None or not in_date_range(listed_dt):
        return None

    price = parse_price(html)
    if price is None:
        return None

    tm = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    title = html_lib.unescape(tm.group(1).strip()) if tm else f"İlan #{source_id}"

    year_spec = spec_value(html, "Yıl") or spec_value(html, "Yil")
    year_title, make_guess, model_guess = parse_title_parts(title)
    year = year_spec or year_title
    model_detail = spec_value(html, "Model")
    make = make_guess
    model = model_detail or model_guess
    tm2 = re.match(r"^\d{4}\s+(.+?)\s+\d", title)
    if tm2 and (make == "" or make == year_title):
        make = tm2.group(1).strip()

    km_raw = spec_value(html, "KM") or spec_value(html, "Kilometre") or ""
    km = re.sub(r"[^\d]", "", km_raw) or None

    photos = sorted(
        set(
            re.findall(
                r"https://kpazar\.com/wp-content/uploads/\d{4}/\d{2}/[^\"']+\.(?:webp|jpg|jpeg|png)",
                html,
                re.I,
            )
        )
    )

    seller_name = ""
    sm = re.search(r'class="ls-seller__name"[^>]*>([^<]+)', html, re.I)
    if sm:
        seller_name = html_lib.unescape(sm.group(1).strip())

    seller_meta = ""
    mm = re.search(r'class="ls-seller__meta"[^>]*>\s*([^<]+(?:<[^>]+>[^<]*)*?)\s*</div>', html, re.I | re.S)
    if mm:
        seller_meta = html_lib.unescape(re.sub(r"<[^>]+>", " ", mm.group(1)))
        seller_meta = re.sub(r"\s+", " ", seller_meta).strip()

    type_label = "Bireysel Satıcı"
    member_since = ""
    if seller_meta:
        parts = [p.strip() for p in re.split(r"[·•]", seller_meta) if p.strip()]
        if parts:
            type_label = parts[0]
        for p in parts:
            ym = re.search(r"(?:üye|uye)\s*(\d{4})", p, re.I)
            if ym:
                member_since = ym.group(1)

    profile = re.sub(r"\s*\d+\s*görüntülenme.*$", "", seller_meta, flags=re.I).strip()
    profile = re.sub(r"\s+", " ", profile)

    gallery = re.search(r'href="(?:https://kpazar\.com)?(/uye/([^"/]+)/)"', html, re.I)
    seller_key = gallery.group(2) if gallery else re.sub(r"[^a-z0-9]+", "-", seller_name.lower()).strip("-")
    profile_url = (BASE + gallery.group(1)) if gallery else ""

    kimden = spec_value(html, "Kimden") or ""
    corp_hint = type_label + " " + kimden + " " + seller_name
    is_corporate = bool(
        re.search(
            r"galeri|kurumsal|yetkili|ltd|limited|motors|otomotiv|trading|car\s|autos",
            corp_hint,
            re.I,
        )
    )

    desc = ""
    dm = re.search(r'class="ls-description[^"]*"[^>]*>(.*?)</div>', html, re.I | re.S)
    if dm:
        desc = html_lib.unescape(re.sub(r"<[^>]+>", "\n", dm.group(1)))
        desc = re.sub(r"\n{3,}", "\n\n", desc).strip()

    loc = ""
    lm = re.search(
        r"(Girne|Lefkoşa|Mağusa|Güzelyurt|Lefke|İskele|Famagusta)\s*/\s*([A-Za-zÇĞİÖŞÜçğıöşü0-9\s\-]+)",
        html,
    )
    if lm:
        loc = f"{lm.group(1).strip()} / {lm.group(2).strip()}"
    else:
        loc = spec_value(html, "Konum") or "KKTC"

    equipment: list[str] = []
    for block in re.findall(r"<h3[^>]*>([^<]+)</h3>\s*<ul[^>]*>(.*?)</ul>", html, re.I | re.S):
        for li in re.findall(r"<li[^>]*>([^<]+)", block[1], re.I):
            t = html_lib.unescape(li.strip())
            if t:
                equipment.append(t)

    return {
        "source": SOURCE,
        "source_id": source_id,
        "source_url": url,
        "title": title,
        "description": desc,
        "location": loc,
        "listed_at": listed_at,
        "listed_at_iso": listed_dt.strftime("%Y-%m-%d"),
        "price": price,
        "price_negotiable": bool(re.search(r"takas|pazarlık|pazarlik", html, re.I)),
        "subcategory": "Otomobil",
        "segment": "otomobil",
        "condition": spec_value(html, "Araç Durumu") or spec_value(html, "Arac Durumu") or "İkinci El",
        "photo_urls": photos,
        "is_corporate": is_corporate,
        "seller_key": seller_key or f"satici-{source_id}",
        "seller_name": seller_name or seller_key.replace("-", " ").title(),
        "seller_type_label": type_label,
        "seller_member_since": member_since,
        "seller_profile_line": profile,
        "seller_profile_url": profile_url,
        "vehicle": {
            "year": year,
            "km": km,
            "fuel": spec_value(html, "Yakıt Tipi") or spec_value(html, "Yakıt Türü"),
            "transmission": spec_value(html, "Vites") or spec_value(html, "Vites Tipi"),
            "body": spec_value(html, "Kasa Tipi"),
            "engine_cc": re.sub(r"[^\d]", "", spec_value(html, "Motor Hacmi") or "") or None,
            "hp": re.sub(r"[^\d]", "", spec_value(html, "Motor Gücü") or spec_value(html, "Motor Gucu") or "") or None,
            "drive": spec_value(html, "Çekiş") or spec_value(html, "Cekis"),
            "color": spec_value(html, "Renk"),
            "make": make,
            "model": model,
        },
        "equipment": equipment[:40],
    }


def download_photos(payload: dict) -> list[str]:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    sid = payload["source_id"]
    local: list[str] = []
    for i, url in enumerate(payload.get("photo_urls") or []):
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if ext not in {".webp", ".jpg", ".jpeg", ".png"}:
            ext = ".webp"
        name = f"kpz_{sid}_{i}{ext}"
        target = PHOTO_DIR / name
        if target.exists() and target.stat().st_size > 0:
            local.append(name)
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                target.write_bytes(r.read())
            local.append(name)
            time.sleep(0.12)
        except Exception:
            pass
    payload["local_photos"] = local
    return local


def main() -> None:
    global DATE_FROM, DATE_TO
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--date-from", default="2026-06-01", help="Baslangic (YYYY-MM-DD)")
    parser.add_argument("--date-to", default="", help="Bitis (YYYY-MM-DD, bos=sinirsiz)")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()

    DATE_FROM = parse_iso_date(args.date_from) or CUTOFF
    DATE_TO = parse_iso_date(args.date_to) if args.date_to else None

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    if args.download_only:
        for fp in sorted(QUEUE_DIR.glob("*.json")):
            data = json.loads(fp.read_text(encoding="utf-8"))
            download_photos(data)
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Fotograflar guncellendi.")
        return

    print("KPazar ilan URL'leri taranıyor...")
    urls = crawl_listing_urls()
    print(f"Toplam URL: {len(urls)}")

    items: list[dict] = []
    for i, url in enumerate(urls, 1):
        try:
            item = parse_listing(url)
        except Exception as ex:
            print(f"  skip {url}: {ex}")
            continue
        if item is None:
            continue
        items.append(item)
        if i % 10 == 0:
            print(f"  taranan {i}/{len(urls)}, uygun {len(items)}")
        time.sleep(0.18)

    items.sort(key=lambda x: (x.get("listed_at_iso") or "", x.get("source_id", 0)))
    if args.limit > 0:
        items = items[: args.limit]

    print(f"{DATE_FROM.date()} — {DATE_TO.date() if DATE_TO else '...'} uygun: {len(items)} ilan")

    for idx, item in enumerate(items, 1):
        download_photos(item)
        out = QUEUE_DIR / f"{idx:04d}_{item['source_id']}.json"
        out.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"  {out.name} | {item['listed_at']} | {item['seller_name']} | "
            f"{item['seller_profile_line'][:50]} | {item['price']}"
        )

    META_FILE.write_text(
        json.dumps(
            {
                "built_at": datetime.now().isoformat(),
                "cutoff": DATE_FROM.isoformat(),
                "date_to": DATE_TO.isoformat() if DATE_TO else "",
                "total": len(items),
                "source": SOURCE,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Kuyruk:", QUEUE_DIR)


if __name__ == "__main__":
    main()
