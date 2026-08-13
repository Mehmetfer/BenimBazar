"""Listing photo storage helpers — DB-first, physical delete only after commit.

Physical files are never unlinked inside an open transaction. Soft-delete markers
are written in-tx; disk purge runs only after a successful COMMIT.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable

from . import db

log = logging.getLogger("changex.media_storage")


def upload_path_for_url(upload_dir: Path, url: str) -> Path | None:
    """Map `/uploads/<fname>` → filesystem path (reject traversal)."""
    s = (url or "").strip()
    if not s.startswith("/uploads/"):
        return None
    name = s.rsplit("/", 1)[-1]
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return None
    path = (upload_dir / name).resolve()
    root = upload_dir.resolve()
    if root not in path.parents and path != root:
        return None
    return path


def listing_references_url(conn, url: str) -> bool:
    """True if any trade_listings.photo_urls JSON still contains url."""
    rows = conn.execute("SELECT photo_urls FROM trade_listings").fetchall()
    for row in rows:
        if url in db.loads(row["photo_urls"], []):
            return True
    return False


def prune_listing_photo_rows(conn, *, listing_id: int, keep_urls: list[str]) -> int:
    """Remove listing_photos rows for URLs no longer on the listing."""
    keep = set(keep_urls)
    rows = conn.execute(
        "SELECT id, url FROM listing_photos WHERE listing_id = ?",
        (listing_id,),
    ).fetchall()
    deleted = 0
    for row in rows:
        if row["url"] not in keep:
            conn.execute("DELETE FROM listing_photos WHERE id = ?", (row["id"],))
            deleted += 1
    return deleted


def mark_unreferenced_for_delete(conn, urls: Iterable[str], *, now: float | None = None) -> list[str]:
    """Soft-delete media_uploads rows with refcount 0. Returns URLs safe to purge after commit."""
    ts = now if now is not None else time.time()
    purge: list[str] = []
    for url in urls:
        if not url or not str(url).startswith("/uploads/"):
            continue
        if listing_references_url(conn, url):
            continue
        row = conn.execute(
            "SELECT id, deleted_at FROM media_uploads WHERE url = ?", (url,)
        ).fetchone()
        if row is None:
            # Legacy file without registry — still candidate for disk purge
            purge.append(url)
            continue
        if row["deleted_at"] is None:
            conn.execute(
                "UPDATE media_uploads SET deleted_at = ? WHERE id = ?",
                (ts, row["id"]),
            )
        purge.append(url)
    return purge


def finalize_storage_deletes(upload_dir: Path, urls: Iterable[str]) -> dict:
    """Physically unlink files AFTER successful DB commit. Never raises to callers."""
    removed = 0
    missing = 0
    errors = 0
    for url in urls:
        path = upload_path_for_url(upload_dir, url)
        if path is None:
            continue
        try:
            if path.is_file():
                path.unlink()
                removed += 1
            else:
                missing += 1
        except OSError as exc:
            errors += 1
            log.warning("storage unlink failed url=%s err=%s", url, exc)
            continue
        # Drop registry row only after successful unlink (or already missing)
        try:
            with db.connect() as conn:
                with db.immediate_tx(conn):
                    # Re-check refs — another listing may have reused the URL (shouldn't)
                    if listing_references_url(conn, url):
                        conn.execute(
                            "UPDATE media_uploads SET deleted_at = NULL WHERE url = ?",
                            (url,),
                        )
                        continue
                    conn.execute("DELETE FROM media_uploads WHERE url = ?", (url,))
        except Exception as exc:  # noqa: BLE001 — cleanup must not break request
            log.warning("media_uploads cleanup failed url=%s err=%s", url, exc)
            errors += 1
    return {"removed": removed, "missing": missing, "errors": errors}


def collect_orphan_urls(conn, *, max_age_seconds: float, now: float | None = None) -> list[str]:
    """
    Orphans:
    - media_uploads with deleted_at set and no listing refs
    - media_uploads never attached to any listing and older than max_age_seconds
    """
    ts = now if now is not None else time.time()
    cutoff = ts - max_age_seconds
    out: list[str] = []
    rows = conn.execute(
        """
        SELECT url, created_at, deleted_at FROM media_uploads
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        url = row["url"]
        if listing_references_url(conn, url):
            continue
        deleted_at = row["deleted_at"]
        created_at = float(row["created_at"] or 0)
        if deleted_at is not None:
            out.append(url)
        elif created_at <= cutoff:
            out.append(url)
    return out


def run_orphan_cleanup(
    upload_dir: Path,
    *,
    max_age_seconds: float = 3600,
    now: float | None = None,
) -> dict:
    """Mark aged unattached uploads, then purge soft-deleted / orphan files after commit."""
    ts = now if now is not None else time.time()
    marked: list[str] = []
    with db.connect() as conn:
        with db.immediate_tx(conn):
            candidates = collect_orphan_urls(
                conn, max_age_seconds=max_age_seconds, now=ts
            )
            marked = mark_unreferenced_for_delete(conn, candidates, now=ts)
    stats = finalize_storage_deletes(upload_dir, marked)
    stats["marked"] = len(marked)
    return stats


def apply_photo_url_change(
    conn,
    *,
    listing_id: int,
    old_urls: list[str],
    new_urls: list[str],
) -> list[str]:
    """
    Sync listing_photos + soft-delete removed unreferenced uploads (in-tx).

    Returns URLs that may be physically deleted AFTER the surrounding transaction commits.
    """
    removed = [u for u in old_urls if u not in set(new_urls)]
    prune_listing_photo_rows(conn, listing_id=listing_id, keep_urls=new_urls)
    if not removed:
        return []
    return mark_unreferenced_for_delete(conn, removed)
