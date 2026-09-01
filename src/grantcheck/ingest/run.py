"""The monthly ingest: download, parse, merge, shard, publish.

Runs in GitHub Actions, not on a user's machine. A user running ``uvx grantcheck`` must
never install this subpackage's dependencies or execute a line of it.

    python -m grantcheck.ingest.run --out build/ --vintage 2026-08

The manifest is written **last** and is the commit point. Until it changes, clients keep
serving the previous vintage consistently, so a failed or partial run cannot corrupt what
users see.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
import zipfile
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

from grantcheck.ingest.build import DatasetVintage, build_index, merge_datasets, write_manifest
from grantcheck.ingest.teos import (
    ParseResult,
    parse_bmf,
    parse_epostcard,
    parse_pub78,
    parse_revocation,
)

USER_AGENT = "grantcheck-ingest (+https://github.com/egeria-corporation/grantcheck)"

BMF_URLS = [f"https://www.irs.gov/pub/irs-soi/eo{n}.csv" for n in (1, 2, 3, 4)]
PUB78_URL = "https://apps.irs.gov/pub/epostcard/data-download-pub78.zip"
REVOCATION_URL = "https://apps.irs.gov/pub/epostcard/data-download-revocation.zip"
EPOSTCARD_URL = "https://apps.irs.gov/pub/epostcard/data-download-epostcard.zip"

# If any dataset quarantines more than this share of its rows, something changed upstream
# and the build stops rather than publishing a quietly degraded index.
QUARANTINE_CEILING = 0.01


def _fetch(url: str) -> tuple[bytes, date | None]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=600) as response:
        body = response.read()
        last_modified = response.headers.get("Last-Modified")
    published = None
    if last_modified:
        try:
            published = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").date()
        except ValueError:
            published = None
    return body, published


def _unzip(blob: bytes) -> str:
    with (
        zipfile.ZipFile(BytesIO(blob)) as archive,
        archive.open(archive.namelist()[0]) as handle,
    ):
        return handle.read().decode("utf-8")


def _check(result: ParseResult, label: str) -> ParseResult:
    rate = result.quarantine_rate()
    print(f"  {label}: {result.ok:,} rows, {result.rejected} quarantined, {result.warned} warnings")
    for line_no, reason, _ in result.quarantined[:5]:
        print(f"      line {line_no}: {reason}")
    if rate > QUARANTINE_CEILING:
        raise SystemExit(
            f"{label}: quarantine rate {rate:.2%} exceeds the {QUARANTINE_CEILING:.0%} "
            "ceiling. The upstream format has probably changed. Refusing to publish a "
            "degraded index — investigate before re-running."
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the published grantcheck index.")
    parser.add_argument("--out", type=Path, default=Path("build"))
    parser.add_argument(
        "--vintage",
        default=datetime.now(UTC).strftime("%Y-%m"),
        help="Index vintage label, YYYY-MM. Defaults to the current month.",
    )
    args = parser.parse_args(argv)

    started = time.time()
    print(f"grantcheck ingest -> {args.out}/{args.vintage}")

    print("downloading and parsing...")
    bmf_rows: list[dict] = []
    bmf_quarantined: list[tuple[int, str, str]] = []
    bmf_warnings: list[tuple[int, str, str]] = []
    bmf_published: date | None = None
    for url in BMF_URLS:
        blob, published = _fetch(url)
        bmf_published = bmf_published or published
        part = parse_bmf(blob.decode("utf-8"))
        bmf_rows += part.rows
        bmf_quarantined += part.quarantined
        bmf_warnings += part.field_warnings
    bmf = _check(
        ParseResult(rows=bmf_rows, quarantined=bmf_quarantined, field_warnings=bmf_warnings),
        "bmf",
    )

    blob, pub78_published = _fetch(PUB78_URL)
    pub78 = _check(parse_pub78(_unzip(blob)), "pub78")

    blob, revocation_published = _fetch(REVOCATION_URL)
    revocation = _check(parse_revocation(_unzip(blob)), "revocation")

    blob, epostcard_published = _fetch(EPOSTCARD_URL)
    epostcard = _check(parse_epostcard(_unzip(blob)), "epostcard")

    print("merging...")
    merged = merge_datasets(bmf=bmf, pub78=pub78, revocation=revocation, epostcard=epostcard)
    print(f"  {len(merged):,} organizations")

    today = datetime.now(UTC).date()
    vintages = [
        DatasetVintage("bmf", bmf_published or today, BMF_URLS[0], bmf.ok),
        DatasetVintage("pub78", pub78_published or today, PUB78_URL, pub78.ok),
        DatasetVintage("revocation", revocation_published or today, REVOCATION_URL, revocation.ok),
        DatasetVintage("epostcard", epostcard_published or today, EPOSTCARD_URL, epostcard.ok),
    ]

    print("building shards...")
    manifest = build_index(
        merged=merged,
        vintages=vintages,
        out_dir=args.out,
        vintage=args.vintage,
        built_at=datetime.now(UTC),
    )

    total = sum(s["bytes"] for s in manifest["shards"])
    largest = max(manifest["shards"], key=lambda s: s["bytes"])
    print(f"  {len(manifest['shards'])} shards, {total / 1048576:.1f} MB")
    print(f"  largest: shard-{largest['prefix']} at {largest['bytes'] / 1048576:.2f} MB")

    # Smoke-test before the commit point. A manifest published over an index that cannot
    # answer for a known organization is worse than no new index at all.
    print("smoke test...")
    for ein, expected in (("271067272", "CODE FOR AMERICA LABS"), ("942278431", "PACKARD")):
        row = merged.get(ein)
        if row is None or expected.split()[0] not in (row.get("name") or ""):
            raise SystemExit(f"smoke test failed for {ein}: got {row and row.get('name')!r}")
        print(f"  {ein}: {row['name']}")

    path = write_manifest(manifest, args.out)
    print(f"\nmanifest written (the commit point): {path}")
    print(f"done in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
