"""Build the SQL to load the whole published index into D1.

Development and deployment tooling, not part of the shipped library. It reuses the published
index rather than re-running the ingest, so what lands in D1 is exactly what the CLI reads —
the two surfaces cannot diverge on the data, only on interpretation, and the parity test
covers interpretation.

Three constraints from D1 shape the output:

  * a single SQL statement may not exceed 100 KB, so rows are batched into multi-row INSERTs
    and each batch is closed before it reaches the limit;
  * `wrangler d1 execute --file` accepts up to 5 GB, but a single enormous file is
    all-or-nothing and gives no progress, so the output is split into numbered parts;
  * the secondary indexes are dropped before the load and recreated after. Maintaining two
    B-trees across 3.2M inserts costs far more than rebuilding them once at the end.

Usage:
    python build_d1_import.py [--shards N] [--out DIR]

    --shards N   stop after N shards. For measuring before committing to a full run.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path

import zstandard

BASE = "https://index.check.opengrants.io"
# Cloudflare answers the default Python-urllib agent with a 403 that never reaches the
# bucket. The same trap has now cost this project three separate debugging sessions.
UA = "grantcheck (+https://github.com/egeria-corporation/grantcheck)"

# Comfortably under D1's 100 KB statement ceiling, with room for one more long row.
MAX_STATEMENT_BYTES = 80_000

# Rows per output file. Small enough that a failure loses minutes rather than an hour.
ROWS_PER_PART = 250_000


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", type=int, default=0, help="stop after N shards (0 = all)")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(fetch(f"{BASE}/manifest.json"))
    shards = manifest["shards"]
    if args.shards:
        shards = shards[: args.shards]

    vintage = manifest["vintage"]
    print(f"index vintage {vintage}, {len(shards)} of {len(manifest['shards'])} shards")

    columns: list[str] = []
    total_rows = 0
    part = 0
    part_rows = 0
    handle = None
    pending: list[str] = []
    pending_bytes = 0

    def open_part() -> None:
        nonlocal handle, part, part_rows
        part += 1
        part_rows = 0
        path = args.out / f"part-{part:03d}.sql"
        handle = path.open("w", encoding="utf-8", newline="\n")

    def flush() -> None:
        """Close the current multi-row INSERT and write it."""
        nonlocal pending, pending_bytes
        if not pending or handle is None:
            return
        handle.write(
            f"INSERT OR REPLACE INTO organization ({','.join(columns)}) VALUES\n"
            + ",\n".join(pending)
            + ";\n"
        )
        pending = []
        pending_bytes = 0

    open_part()
    with tempfile.TemporaryDirectory() as work:
        for n, shard in enumerate(shards, 1):
            blob = fetch(f"{BASE}/{vintage}/{shard['file']}")
            raw = zstandard.ZstdDecompressor().decompress(blob, max_output_size=2 * 1024**3)
            db_path = Path(work) / "shard.sqlite"
            db_path.write_bytes(raw)

            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM organization")
            if not columns:
                columns = [d[0] for d in cursor.description]

            for row in cursor:
                tuple_sql = "(" + ",".join(literal(row[c]) for c in columns) + ")"
                if pending_bytes + len(tuple_sql) > MAX_STATEMENT_BYTES:
                    flush()
                pending.append(tuple_sql)
                pending_bytes += len(tuple_sql) + 2
                total_rows += 1
                part_rows += 1

                if part_rows >= ROWS_PER_PART:
                    flush()
                    if handle:
                        handle.close()
                    open_part()
            conn.close()
            db_path.unlink()

            if n % 20 == 0 or n == len(shards):
                print(f"  {n}/{len(shards)} shards, {total_rows:,} rows", flush=True)

    flush()
    if handle:
        handle.close()

    # The vintage rows and the index rebuild go in their own files so they can be applied in
    # the right order without hunting through the parts.
    (args.out / "000-pre.sql").write_text(
        "DROP INDEX IF EXISTS idx_org_state_name;\nDROP INDEX IF EXISTS idx_org_name;\n",
        encoding="utf-8",
        newline="\n",
    )
    vintage_sql = "\n".join(
        "INSERT OR REPLACE INTO dataset_vintage (dataset, published, source_url, row_count) "
        f"VALUES ({literal(d['dataset'])},{literal(d['published'])},"
        f"{literal(d['source_url'])},{d['row_count']});"
        for d in manifest["datasets"]
    )
    (args.out / "999-post.sql").write_text(
        "CREATE INDEX IF NOT EXISTS idx_org_state_name ON organization(state, name);\n"
        "CREATE INDEX IF NOT EXISTS idx_org_name ON organization(name);\n" + vintage_sql + "\n",
        encoding="utf-8",
        newline="\n",
    )

    parts = sorted(args.out.glob("part-*.sql"))
    total_bytes = sum(p.stat().st_size for p in parts)
    print(f"\n{total_rows:,} rows in {len(parts)} parts, {total_bytes / 1024**2:,.0f} MB of SQL")
    if total_rows:
        print(f"{total_bytes / total_rows:.0f} bytes of SQL per row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
