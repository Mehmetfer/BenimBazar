#!/usr/bin/env python3
"""
kibrisarabaal.com -> BenimBazar import kuyrugu.
Varsayilan: 1 Agustos 2026 — bugun, fiyatli ve tum ozellikleri dolu ilanlar.

Kullanim:
  python scripts/kibrisarabaal_build_queue.py
  python scripts/kibrisarabaal_build_queue.py --date-from 2026-08-01 --date-to 2026-08-19
  python scripts/kibrisarabaal_build_queue.py --fresh --limit 5
  python scripts/kibrisarabaal_build_queue.py --download-only
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT / "php-site" / "storage" / "kka-queue"
PHOTO_DIR = ROOT / "php-site" / "uploads" / "ext-import"
STATE_FILE = ROOT / "scripts" / ".kka-queue-meta.json"

BASE = "https://kibrisarabaal.com"
ARCHIVE = f"{BASE}/arac-kibris-2-el-araba/"
CUTOFF = datetime(2026, 8, 1)
DATE_FROM = CUTOFF
DATE_TO: datetime | None = datetime.now()
MIN_PHOTOS = 3
UA = "Mozilla/5.0 (compatible; ChangeXImport/1.0)"

TR_MONTHS = {
    "ocak": 1,
    "subat": 2,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8,
    "ağustos": 8,
    "eylul": 9,
    "eylül": 9,
    "ekim": 10,
    "kasim": 11,
    "kasım": 11,
    "aralik": 12,
    "aralık": 12,
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def parse_tr_date(text: str) -> datetime | None:
    text = text.strip().lower()
    m = re.search(r"(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})", text)
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2), int(m.group(3))
    month = TR_MONTHS.get(mon)
    if not month:
        return None
    return datetime(year, month, day)


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


def extract_listing_paths(html: str) -> list[str]:
    paths: list[str] = []
    for m in re.finditer(
        r'(?:href|window\.location\.href)\s*=\s*["\'](?:https://kibrisarabaal\.com)?(/ilan/\d+-[^"\']+)["\']',
        html,
        re.I,
    ):
        path = m.group(1).split("?")[0].rstrip("/") + "/"
        if path not in paths:
            paths.append(path)
    return paths


def crawl_listing_urls() -> list[str]:
    seen: set[str] = set()
    page = 1
    stale_pages = 0
    while page <= 200:
        url = ARCHIVE if page == 1 else f"{ARCHIVE}?page={page}"
        try:
            html = fetch(url)
        except Exception as ex:
            print(f"  crawl page {page} hata: {ex}")
            break
        paths = extract_listing_paths(html)
        if not paths:
            break
        new = 0
        for path in paths:
            full = BASE + path if path.startswith("/") else path
            if full not in seen:
                seen.add(full)
                new += 1
        if new == 0:
            stale_pages += 1
            if stale_pages >= 2:
                break
        else:
            stale_pages = 0
        page += 1
        time.sleep(0.25)
    return sorted(seen, key=lambda u: int(re.search(r"/ilan/(\d+)-", u).group(1)) if re.search(r"/ilan/(\d+)-", u) else 0)


def spec_value(html: str, label: str) -> str | None:
    patterns = [
        rf"{re.escape(label)}:\s*</span>\s*<span[^>]*>\s*([^<]+)\s*</span>",
        rf"{re.escape(label)}[^<]*</[^>]+>\s*<[^>]+>\s*([^<]+)",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I | re.S)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


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
    # Oncelik: sterlin (KKTC). Yalnizca TL varsa TRY.
    js = re.search(
        r"price\s*=\s*['\"]([\d.,]+)\s*(?:£|STG|Stg|stg)['\"]",
        html,
        re.I,
    )
    if js:
        amt = parse_amount(js.group(1))
        if amt > 0:
            return {"currency": "GBP", "amount": amt}

    for pat in [
        r"([\d.,]+)\s*(?:£|STG|Stg|stg)\b",
        r"Nakit[^<\n]{0,40}?([\d.,]+)\s*(?:STG|Stg|stg)",
    ]:
        m = re.search(pat, html, re.I)
        if m:
            amt = parse_amount(m.group(1))
            if amt > 0:
                return {"currency": "GBP", "amount": amt}

    # Saf TL ilani (sterlin yok, ≈ donusum satiri haric)
    if not re.search(r"(?:£|STG|Stg|stg)", html, re.I):
        for pat in [
            r"([\d.,]+)\s*TL\b",
            r"([\d.,]+)\s*₺",
            r"([\d.,]+)\s*TRY\b",
        ]:
            m = re.search(pat, html, re.I)
            if m:
                amt = parse_amount(m.group(1))
                if amt > 0:
                    return {"currency": "TRY", "amount": amt}
    return None


def parse_title_parts(title: str) -> tuple[str, str, str]:
    title = re.sub(r"\s+", " ", title.strip())
    m = re.match(
        r"^(?:(\d{4})\s+Model\s+)?(?:(Otomatik|Manuel|Düz|Yarı\s+Otomatik)\s+)?(.+)$",
        title,
        re.I,
    )
    if not m:
        return "", "", title
    year = m.group(1) or ""
    rest = (m.group(3) or "").strip()
    parts = rest.rsplit(" ", 1)
    if len(parts) == 2 and parts[0]:
        make, model = parts[0], parts[1]
    else:
        make, model = rest, ""
    return year, make, model


def parse_corporate_seller(html: str, gallery_slug: str | None) -> dict:
    out: dict = {
        "seller_name": "",
        "seller_type_label": "",
        "seller_member_since": "",
        "seller_member_date": "",
        "seller_profile_url": "",
        "gallery_about": "",
    }
    corp = re.search(
        r"([^<\n]{3,120}?)\s+Kurumsal\s+(?:Üye|Uye)[^<\n]*?(?:Üyelik|Uyelik)\s*tarihi:\s*(\d{1,2}\s+[A-Za-zçğıöşüÇĞİÖŞÜ]+\s+\d{4})",
        html,
        re.I | re.S,
    )
    if corp:
        out["seller_name"] = re.sub(r"\s+", " ", corp.group(1)).strip()
        out["seller_type_label"] = "Kurumsal Galeri"
        member_dt = parse_tr_date(corp.group(2))
        if member_dt:
            out["seller_member_since"] = str(member_dt.year)
        out["seller_member_date"] = corp.group(2).strip()
    if gallery_slug:
        out["seller_profile_url"] = f"{BASE}/galeri/{gallery_slug}/"
        if not out["seller_name"]:
            out["seller_name"] = gallery_slug.replace("-", " ").title()
    about = re.search(r"Galeri Hakkında[\s\S]{0,4000}?</h[^>]*>[\s\S]{0,2000}", html, re.I)
    if about:
        chunk = re.sub(r"<[^>]+>", " ", about.group(0))
        chunk = re.sub(r"\s+", " ", chunk).strip()
        chunk = re.sub(r"^Galeri Hakkında\s*", "", chunk, flags=re.I).strip()
        if len(chunk) > 20:
            out["gallery_about"] = chunk[:500]
    return out


def parse_equipment(html: str) -> list[str]:
    items: list[str] = []
    for label in ("Donanım", "Donanim", "Özellikler", "Ozellikler", "Ekstra"):
        block = re.search(
            rf"{re.escape(label)}[\s\S]{{0,3000}}?(?:</ul>|</div>)",
            html,
            re.I,
        )
        if not block:
            continue
        for li in re.findall(r"<li[^>]*>([^<]+)</li>", block.group(0), re.I):
            text = re.sub(r"\s+", " ", li).strip()
            if text and text not in items:
                items.append(text)
    return items[:40]


def is_blank(value: object) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s in ("", "-", "—", "0", "null", "None")


def is_complete(payload: dict) -> bool:
    price = payload.get("price") or {}
    amount = float(price.get("amount") or 0)
    if amount <= 0:
        return False
    photos = payload.get("photo_urls") or []
    if len(photos) < MIN_PHOTOS:
        return False
    loc = str(payload.get("location") or "").strip()
    if loc == "" or loc.lower() == "kktc":
        return False
    vehicle = payload.get("vehicle") or {}
    # km ve renk esnetildi; yil + temel arac alanlari zorunlu
    required = ("year", "fuel", "transmission", "body", "make", "model")
    for key in required:
        if is_blank(vehicle.get(key)):
            return False
    return True


def parse_listing(url: str) -> dict | None:
    html = fetch(url)
    source_id = int(re.search(r"/ilan/(\d+)-", url).group(1))

    listed_at = spec_value(html, "İlan Tarihi") or spec_value(html, "Ilan Tarihi")
    listed_dt = parse_tr_date(listed_at or "")
    if listed_dt is None:
        return None
    if not in_date_range(listed_dt):
        return None

    price = parse_price(html)
    if price is None:
        return None

    title_m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    title = title_m.group(1).strip() if title_m else f"İlan #{source_id}"

    year_spec = spec_value(html, "Yıl") or spec_value(html, "Yil")
    year_title, make, model = parse_title_parts(title)
    year = year_spec or year_title

    km_raw = spec_value(html, "Kilometre") or ""
    km = re.sub(r"[^\d]", "", km_raw) or None

    photos = sorted(
        set(
            re.findall(
                r"https://kibrisarabaal\.com/uploads/listings/\d+/img_[^\"']+\.(?:webp|jpg|jpeg|png)",
                html,
                re.I,
            )
        )
    )

    gallery = re.search(r'href="(?:https://kibrisarabaal\.com)?(/galeri/([^"/]+)/)"', html)
    gallery_slug = gallery.group(2) if gallery else None
    is_corporate = bool(re.search(r"Kurumsal", html, re.I)) or gallery_slug is not None
    corp = parse_corporate_seller(html, gallery_slug)

    seller_key = gallery_slug if gallery_slug else f"bireysel-{source_id}"
    seller_name = corp.get("seller_name") or (gallery_slug.replace("-", " ").title() if gallery_slug else "Bireysel")

    phone = None
    pm = re.search(r"(?:\+90|0)\s*[\d\s]{10,14}", html)
    if pm:
        phone = re.sub(r"\s+", " ", pm.group(0)).strip()

    desc = ""
    dm = re.search(r'class="[^"]*listing-description[^"]*"[^>]*>(.*?)</div>\s*<', html, re.I | re.S)
    if dm:
        desc = re.sub(r"<style[\s\S]*?</style>", "", dm.group(1), flags=re.I)
        desc = re.sub(r"<[^>]+>", "\n", desc)
        desc = re.sub(r"\.listing-description[^\n]*", "", desc)
        desc = re.sub(r"\n{3,}", "\n\n", desc).strip()

    loc = ""
    for pat in [
        r"(Girne|Lefkoşa|Mağusa|Güzelyurt|Lefke|İskele)\s*/\s*([A-Za-zÇĞİÖŞÜçğıöşü0-9\s\-]+)",
        r"(Girne|Lefkoşa|Mağusa|Güzelyurt|Lefke|İskele)\s*,\s*([A-Za-zÇĞİÖŞÜçğıöşü0-9\s\-]+)",
    ]:
        lm = re.search(pat, html)
        if lm:
            loc = f"{lm.group(1).strip()} / {lm.group(2).strip()}"
            break
    if not loc:
        loc = "KKTC"

    payload = {
        "source": "kibrisarabaal.com",
        "source_id": source_id,
        "source_url": url,
        "title": title,
        "description": desc,
        "location": loc.replace("/", ", "),
        "listed_at": listed_at,
        "listed_at_iso": listed_dt.strftime("%Y-%m-%d"),
        "price": price,
        "price_negotiable": bool(re.search(r"pazarlık|pazarlik|takas", html, re.I)),
        "subcategory": "Otomobil",
        "segment": "otomobil",
        "condition": spec_value(html, "Araç Durumu") or spec_value(html, "Arac Durumu") or "2.El",
        "photo_urls": photos,
        "is_corporate": is_corporate,
        "seller_key": seller_key,
        "seller_name": seller_name,
        "seller_phone": phone,
        "seller_type_label": corp.get("seller_type_label") or ("Kurumsal Galeri" if is_corporate else "Sahibinden"),
        "seller_member_since": corp.get("seller_member_since") or "",
        "seller_member_date": corp.get("seller_member_date") or "",
        "seller_profile_url": corp.get("seller_profile_url") or "",
        "gallery_about": corp.get("gallery_about") or "",
        "equipment": parse_equipment(html),
        "vehicle": {
            "year": year,
            "km": km,
            "fuel": spec_value(html, "Yakıt Türü") or spec_value(html, "Yakit Turu"),
            "transmission": spec_value(html, "Vites Tipi"),
            "body": spec_value(html, "Kasa Tipi"),
            "engine_cc": re.sub(r"[^\d]", "", spec_value(html, "Motor Hacmi (cc)") or spec_value(html, "Motor Hacmi") or "") or None,
            "color": spec_value(html, "Renk"),
            "drive": spec_value(html, "Direksiyon Tipi") or spec_value(html, "Direksiyon"),
            "make": make,
            "model": model,
        },
    }
    if price["currency"] != "GBP" and price["currency"] != "TRY":
        return None
    if not is_complete(payload):
        return None
    return payload


def download_photos(payload: dict) -> list[str]:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    local: list[str] = []
    sid = payload["source_id"]
    for i, url in enumerate(payload.get("photo_urls") or []):
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if ext not in {".webp", ".jpg", ".jpeg", ".png"}:
            ext = ".webp"
        name = f"kka_{sid}_{i}{ext}"
        target = PHOTO_DIR / name
        if target.exists() and target.stat().st_size > 0:
            local.append(name)
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                target.write_bytes(r.read())
            local.append(name)
            time.sleep(0.15)
        except Exception:
            pass
    payload["local_photos"] = local
    return local


def main() -> None:
    global DATE_FROM, DATE_TO
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max ilan (0=tumu)")
    parser.add_argument("--date-from", default="2026-08-01", help="Baslangic (YYYY-MM-DD)")
    parser.add_argument("--date-to", default=datetime.now().strftime("%Y-%m-%d"), help="Bitis (YYYY-MM-DD)")
    parser.add_argument("--fresh", action="store_true", help="Eski kuyruk dosyalarini sil")
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()

    DATE_FROM = parse_iso_date(args.date_from) or CUTOFF
    DATE_TO = parse_iso_date(args.date_to) if args.date_to else datetime.now()

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    if args.fresh and not args.download_only:
        for fp in QUEUE_DIR.glob("*.json"):
            fp.unlink()
        print("Eski kuyruk silindi.")

    if args.download_only:
        for fp in sorted(QUEUE_DIR.glob("*.json")):
            data = json.loads(fp.read_text(encoding="utf-8"))
            download_photos(data)
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Fotograflar guncellendi.")
        return

    print("Ilan URL'leri taranıyor...")
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
        if i % 20 == 0:
            print(f"  taranan {i}/{len(urls)}, uygun {len(items)}")
        time.sleep(0.2)

    items.sort(key=lambda x: (x.get("listed_at_iso") or "", x.get("source_id", 0)))

    if args.limit > 0:
        items = items[: args.limit]

    print(f"{DATE_FROM.date()} — {DATE_TO.date() if DATE_TO else '...'} uygun ilan: {len(items)} (eskiden yeniye)")

    for idx, item in enumerate(items, 1):
        download_photos(item)
        out = QUEUE_DIR / f"{idx:04d}_{item['source_id']}.json"
        out.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  queue {out.name} | {item['listed_at']} | {item['title'][:50]} | {item['price']}")

    meta = {
        "built_at": datetime.now().isoformat(),
        "cutoff": DATE_FROM.isoformat(),
        "date_to": DATE_TO.isoformat() if DATE_TO else "",
        "total": len(items),
        "sorted": "listed_at asc",
        "filters": "price_required,gpb_or_try,year+fuel+trans+body+make+model,min_photos=" + str(MIN_PHOTOS),
    }
    STATE_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (QUEUE_DIR / ".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Kuyruk hazir:", QUEUE_DIR)


if __name__ == "__main__":
    main()
