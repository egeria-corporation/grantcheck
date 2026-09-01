"""Seed a local D1 from the published index, so `wrangler dev` serves real organizations.

Development convenience only. Production loading is a chunked import in the ingest
workflow, which reuses the Python parsers rather than reimplementing them.

Python rather than shelling out to zstd and sqlite3, because neither CLI is reliably
present on a development machine and both are in the standard library or an existing
dependency.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path

import zstandard

BASE = os.environ.get("INDEX_BASE", "https://index.check.opengrants.io")
# Cloudflare returns 403 to a default agent. The real client sets this for the same reason.
UA = "grantcheck (+https://github.com/egeria-corporation/grantcheck)"
PREFIXES = os.environ.get("SEED_PREFIXES", "27,94,20,53,36,13,00,01").split(",")
PER_SHARD = int(os.environ.get("SEED_PER_SHARD", "300"))

# Always seeded, whatever the sampling picks up: these are the organizations the README,
# the landing page, and the demos reference. A seeded site where the documented example
# returns not-found is worse than an empty one.
ALWAYS = [
    "271067272",  # Code for America Labs — the README example
    "942278431",  # Packard Foundation — the private foundation warning
    "942614101",  # Second Harvest of Silicon Valley
    "530196605",  # American National Red Cross
    "363673599",  # Feeding America
    "135562976",  # Boys & Girls Clubs of America — a central organization
    "001037180",  # revoked, reinstated, revoked again
    "000003154",  # revoked and never reinstated
]

OUT = Path(__file__).parent.parent / "seed.sql"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def main() -> int:
    manifest = json.loads(fetch(f"{BASE}/manifest.json"))
    print(f"index vintage {manifest['vintage']}, {len(manifest['shards'])} shards available")

    rows: list[dict] = []
    columns: list[str] = []
    with tempfile.TemporaryDirectory() as work:
        # A heavily used two-digit prefix is split into three-digit shards, so an exact
        # match misses it entirely — which is how prefix 27, where the README's example
        # organization lives, was silently skipped.
        wanted = []
        for prefix in PREFIXES:
            matches = [s for s in manifest["shards"] if s["prefix"].startswith(prefix)]
            if not matches:
                print(f"  prefix {prefix}: no shard, skipping")
                continue
            wanted.extend(matches[:2])

        for shard in wanted:
            prefix = shard["prefix"]

            blob = fetch(f"{BASE}/{manifest['vintage']}/{shard['file']}")
            raw = zstandard.ZstdDecompressor().decompress(blob, max_output_size=512 * 1024 * 1024)
            db_path = Path(work) / f"{prefix}.sqlite"
            db_path.write_bytes(raw)

            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            # Prefer organizations with a full record, so the seeded site shows real reports
            # rather than a page of not-found placeholders.
            pinned = [e for e in ALWAYS if e.startswith(prefix)]
            got = conn.execute(
                "SELECT * FROM organization ORDER BY in_bmf DESC, in_pub78 DESC, name LIMIT ?",
                (PER_SHARD,),
            ).fetchall()
            if pinned:
                placeholders = ",".join("?" for _ in pinned)
                got = list(got) + conn.execute(
                    f"SELECT * FROM organization WHERE ein IN ({placeholders})", pinned
                ).fetchall()
            conn.close()

            if got and not columns:
                columns = list(got[0].keys())
            rows.extend(dict(r) for r in got)
            print(f"  prefix {prefix}: {len(got)} rows")

    if not rows:
        print("no rows fetched", file=sys.stderr)
        return 1

    def literal(value: object) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    lines = [
        "INSERT OR REPLACE INTO dataset_vintage (dataset, published, source_url, row_count) "
        f"VALUES ({literal(d['dataset'])},{literal(d['published'])},"
        f"{literal(d['source_url'])},{d['row_count']});"
        for d in manifest["datasets"]
    ]
    column_list = ",".join(columns)
    lines.extend(
        f"INSERT OR REPLACE INTO organization ({column_list}) VALUES "
        f"({','.join(literal(r[c]) for c in columns)});"
        for r in rows
    )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.name}: {len(rows):,} organizations, {len(manifest['datasets'])} vintages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
