"""Back up the account data from D1.

`wrangler d1 export` refuses a database containing virtual tables, and this one has an FTS5
index over organization names. That is a deliberate trade: full-text search is worth far more
than a whole-database export of data that is 97% derived. But the trade is only safe if the
part that is *not* derived still gets backed up, which is what this does.

What is worth backing up, and what is not:

  * `organization` and `dataset_vintage` are derived. Every row comes from the published R2
    index and can be rebuilt exactly by `build_d1_import.py`. Backing them up would be
    backing up a cache.
  * `account` and `roster_entry` exist nowhere else. If they are lost, they are lost - a
    person's saved organizations cannot be reconstructed from anything.
  * `session` and `login_token` are deliberately EXCLUDED. They hold live credentials, and a
    backup of live credentials is a liability, not an asset. Restoring one would resurrect
    sessions that had been signed out and links that had been used. Losing them signs
    everybody out, which is a minor inconvenience with a one-click fix.

Usage:
    python backup_accounts.py [--db grantcheck] [--out DIR] [--local]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Only these. See the module docstring for why sessions and login tokens are not here.
TABLES = ["account", "roster_entry"]


def literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def query(db: str, sql: str, local: bool) -> list[dict]:
    command = [
        "npx",
        "wrangler",
        "d1",
        "execute",
        db,
        "--local" if local else "--remote",
        "--command",
        sql,
        "--json",
    ]
    # shell=True on Windows, where npx is a .cmd and cannot be exec'd directly.
    result = subprocess.run(
        command, capture_output=True, text=True, shell=sys.platform == "win32", check=False
    )
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"wrangler failed on: {sql}")
    # wrangler prints a banner before the JSON; find where the payload starts.
    start = result.stdout.find("[")
    if start < 0:
        raise SystemExit(f"no JSON in wrangler output for: {sql}")
    return json.loads(result.stdout[start:])[0]["results"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="grantcheck")
    parser.add_argument("--out", type=Path, default=Path("backups"))
    parser.add_argument("--local", action="store_true", help="back up the local dev database")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = args.out / f"accounts-{stamp}.sql"

    lines = [
        f"-- grantcheck account backup, {stamp}",
        "-- Restore with: wrangler d1 execute <db> --remote --file=<this file>",
        "-- Excludes session and login_token by design: they are live credentials.",
        "",
    ]
    counts = {}
    for table in TABLES:
        rows = query(args.db, f"SELECT * FROM {table}", args.local)
        counts[table] = len(rows)
        if not rows:
            continue
        columns = list(rows[0].keys())
        lines.append(f"-- {table}: {len(rows)} rows")
        lines.extend(
            f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES "
            f"({','.join(literal(r[c]) for c in columns)});"
            for r in rows
        )
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    summary = ", ".join(f"{n} {t}" for t, n in counts.items())
    print(f"wrote {path} ({summary})")

    if sum(counts.values()) == 0:
        print("\nNothing to back up yet - no accounts exist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
