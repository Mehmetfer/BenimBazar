"""Chain Engine V1 performance benchmark — fixture sizes 100..10k.

Reports p50/p95/p99 for candidate generation + cycle detection (no RPS claims).
Run: PYTHONPATH=/workspace .venv/bin/python -m changex.tests.bench_chain_engine
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path
import tempfile

from changex.app import db
from changex.app.matching import config as matching_config
from changex.app.matching.engine import run_chain_match
from changex.app.domain_status import InventoryStatus, ModerationStatus, TradePreference
from changex.app.value import MANDAL_PER_MADALYON


CATEGORIES = ["Otomobil", "Telefon", "Spor", "Kitap", "Elektronik"]
# Cycle pattern: each wants next category
WANT = {
    "Otomobil": "Telefon",
    "Telefon": "Spor",
    "Spor": "Kitap",
    "Kitap": "Elektronik",
    "Elektronik": "Otomobil",
}


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _seed_fixtures(conn, n: int) -> tuple[int, int]:
    """Insert n chain-eligible listings across rotating categories/owners."""
    now = time.time()
    seed_listing_id = None
    seed_owner_id = None
    for i in range(n):
        cat = CATEGORIES[i % len(CATEGORIES)]
        want = WANT[cat]
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,?)",
            (f"bench_u_{n}_{i}", db.hash_password("x"), "user", now),
        )
        owner_id = int(cur.lastrowid)
        cur = conn.execute(
            """
            INSERT INTO trade_listings(
              owner_id, title, description, category, subcategory, condition, location,
              mandal_units, accept_categories, wanted_items, min_mandal_units, max_mandal_units,
              photo_urls, status, version, moderation_version, created_at, updated_at,
              moderation_status, inventory_status, chain_opt_in, trade_preference,
              brand, model_name, attributes, wanted_categories, wanted_subcategories,
              wanted_brands, wanted_locations, wanted_value_min, wanted_value_max,
              value_gap_tolerance, location_city, location_district, location_country
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                owner_id,
                f"Item-{n}-{i}",
                "bench",
                cat,
                "",
                "good",
                "Istanbul",
                MANDAL_PER_MADALYON,
                db.dumps([]),
                "",
                0,
                0,
                db.dumps([]),
                "APPROVED",
                1,
                1,
                now,
                now,
                ModerationStatus.APPROVED.value,
                InventoryStatus.AVAILABLE.value,
                1,
                TradePreference.CHAIN_ALLOWED.value,
                "",
                "",
                db.dumps({}),
                db.dumps([want]),
                db.dumps([]),
                db.dumps([]),
                db.dumps([]),
                0,
                0,
                0,
                "Istanbul",
                "",
                "",
            ),
        )
        lid = int(cur.lastrowid)
        if i == 0:
            seed_listing_id = lid
            seed_owner_id = owner_id
    return int(seed_listing_id), int(seed_owner_id)


def bench_size(n: int, rounds: int = 7) -> dict:
    matching_config.CHANGE_CHAIN_ENABLED = True
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bench.db"
        db.DB_PATH = path
        db.init_db(path)
        with db.connect() as conn:
            with db.immediate_tx(conn):
                seed_id, owner_id = _seed_fixtures(conn, n)
            times = []
            last = None
            for _ in range(rounds):
                t0 = time.perf_counter()
                with db.connect() as c2:
                    last = run_chain_match(
                        c2,
                        seed_listing_id=seed_id,
                        actor_id=owner_id,
                        max_length=4,
                        max_results=10,
                        persist=False,
                    )
                times.append((time.perf_counter() - t0) * 1000.0)
            times.sort()
            return {
                "n": n,
                "rounds": rounds,
                "p50_ms": round(_percentile(times, 50), 3),
                "p95_ms": round(_percentile(times, 95), 3),
                "p99_ms": round(_percentile(times, 99), 3),
                "candidate_node_count": last["candidate_node_count"] if last else 0,
                "edge_count": last["edge_count"] if last else 0,
                "cycle_count": last["cycle_count"] if last else 0,
            }


def main() -> None:
    sizes = [100, 500, 1000, 5000, 10000]
    rows = []
    for n in sizes:
        # Fewer rounds for large graphs
        rounds = 5 if n <= 1000 else 3
        print(f"benchmarking n={n} ...", flush=True)
        rows.append(bench_size(n, rounds=rounds))
        print(rows[-1], flush=True)
    print("\n=== CHANGE CHAIN ENGINE V1 BENCHMARK ===")
    for r in rows:
        print(
            f"n={r['n']:>5}  p50={r['p50_ms']:>8}ms  p95={r['p95_ms']:>8}ms  "
            f"p99={r['p99_ms']:>8}ms  candidates={r['candidate_node_count']}  "
            f"edges={r['edge_count']}  cycles={r['cycle_count']}"
        )


if __name__ == "__main__":
    main()
