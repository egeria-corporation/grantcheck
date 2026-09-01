"""Build the published index: sharded SQLite, compressed, with a manifest.

This is the design that makes the sixty-second quickstart possible, and it is the central
engineering problem of the tool. The four IRS datasets are about 6.2M rows and 487 MB of
source. A user checking one EIN must not download that.

**Shard by EIN prefix.** The first two digits are a stable, well-distributed partition key,
so a user checking one organization downloads roughly one ninetieth of the data. Each shard
is a standalone SQLite database holding one denormalized row per EIN — denormalized on
purpose, so a check is one indexed lookup rather than five joins — plus a ``meta`` table
carrying the dataset vintages.

Published layout, relative to the index base URL: ``<vintage>/manifest.json`` and
``<vintage>/shard-<NN>.sqlite.zst``.

The manifest is written last and is the commit point. Until it changes, clients keep
serving the previous vintage consistently.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import zstandard

from grantcheck.ingest.teos import ParseResult

MANIFEST_VERSION = 1

# Target compressed size per shard. Prefixes are unevenly distributed, so a handful run
# large; anything over this is split by the third digit into shard-{NNN}. The client
# resolves the most specific shard available, so both shapes coexist in one manifest.
SHARD_TARGET_BYTES = 8 * 1024 * 1024

SCHEMA = """
CREATE TABLE organization (
    ein                      TEXT PRIMARY KEY,

    -- Presence flags. An EIN can appear in one dataset and not another: an organization
    -- dropped from the Business Master File can still sit on the revocation list. A null
    -- BMF column means "not in the BMF", which is different from "in the BMF with no
    -- value", and the checks must be able to tell those apart.
    in_bmf                   INTEGER NOT NULL DEFAULT 0,
    in_pub78                 INTEGER NOT NULL DEFAULT 0,
    in_revocation            INTEGER NOT NULL DEFAULT 0,
    in_epostcard             INTEGER NOT NULL DEFAULT 0,

    -- Business Master File
    name                     TEXT,
    sort_name                TEXT,
    city                     TEXT,
    state                    TEXT,
    zip                      TEXT,
    group_exemption          TEXT,
    affiliation              TEXT,   -- 7 and 9 mean covered by another's group ruling
    subsection               TEXT,
    classification           TEXT,
    ruling                   TEXT,   -- YYYY-MM; the BMF has month precision only
    deductibility            TEXT,
    foundation               TEXT,
    organization_form        TEXT,
    exempt_status            TEXT,
    tax_period               TEXT,   -- YYYY-MM; NOT a filing date
    filing_req_cd            TEXT,
    pf_filing_req_cd         TEXT,
    acct_pd                  TEXT,   -- fiscal year-end month, "01".."12"
    ntee_cd                  TEXT,

    -- Publication 78
    pub78_deductibility_code TEXT,

    -- Automatic Revocation. Presence here does NOT mean currently revoked; read the dates.
    revocation_date          TEXT,   -- ISO 8601
    revocation_posting_date  TEXT,
    reinstatement_date       TEXT,

    -- Form 990-N (e-Postcard). Filing recency MUST union this with the e-file index, or
    -- every small filer in the country is reported as three years delinquent.
    epostcard_tax_year       TEXT,
    epostcard_period_end     TEXT,   -- ISO 8601

    -- SAM.gov public tier, from the monthly entity extract. Populated at M5.
    uei                      TEXT,
    sam_status               TEXT,
    sam_expiration           TEXT,
    sam_purpose              TEXT,
    sam_match_confidence     REAL,
    sam_match_method         TEXT
);

CREATE INDEX idx_org_state_name ON organization(state, name);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_ORG_COLUMNS = [
    "ein", "in_bmf", "in_pub78", "in_revocation", "in_epostcard",
    "name", "sort_name", "city", "state", "zip", "group_exemption", "affiliation",
    "subsection", "classification", "ruling", "deductibility", "foundation",
    "organization_form", "exempt_status", "tax_period", "filing_req_cd",
    "pf_filing_req_cd", "acct_pd", "ntee_cd", "pub78_deductibility_code", "revocation_date",
    "revocation_posting_date", "reinstatement_date", "epostcard_tax_year",
    "epostcard_period_end", "uei", "sam_status", "sam_expiration", "sam_purpose",
    "sam_match_confidence", "sam_match_method",
]  # fmt: skip


@dataclass(frozen=True)
class DatasetVintage:
    """What a source declares about itself, not when we fetched it."""

    dataset: str
    published: date
    source_url: str
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "published": self.published.isoformat(),
            "source_url": self.source_url,
            "row_count": self.row_count,
        }


def _iso(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _revocation_sort_key(row: dict) -> tuple[date, date]:
    """Order revocation rows so the most recent event wins.

    Revocation date first, posting date as the tiebreak. ``date.min`` stands in for a
    missing date so a row with no dates never outranks one that has them.
    """
    return (
        row.get("revocation_date") or date.min,
        row.get("revocation_posting_date") or date.min,
    )


def merge_datasets(
    *,
    bmf: ParseResult,
    pub78: ParseResult,
    revocation: ParseResult,
    epostcard: ParseResult,
) -> dict[str, dict]:
    """Join the four datasets on EIN into one denormalized row per organization.

    The union of EINs, not the intersection. An organization present only on the revocation
    list still needs a row, or the tool would report it as not found when it is in fact
    revoked — which is the wrong answer in the most consequential direction.
    """
    merged: dict[str, dict] = defaultdict(
        lambda: (
            dict.fromkeys(_ORG_COLUMNS)
            | {"in_bmf": 0, "in_pub78": 0, "in_revocation": 0, "in_epostcard": 0}
        )
    )

    for row in bmf.rows:
        r = merged[row["ein"]]
        r.update(
            ein=row["ein"],
            in_bmf=1,
            name=row["name"],
            sort_name=row["sort_name"],
            city=row["city"],
            state=row["state"],
            zip=row["zip"],
            group_exemption=row["group_exemption"],
            affiliation=row["affiliation"],
            subsection=row["subsection"],
            classification=row["classification"],
            ruling=row["ruling"],
            deductibility=row["deductibility"],
            foundation=row["foundation"],
            organization_form=row["organization"],
            exempt_status=row["status"],
            tax_period=row["tax_period"],
            filing_req_cd=row["filing_req_cd"],
            pf_filing_req_cd=row["pf_filing_req_cd"],
            acct_pd=row["acct_pd"],
            ntee_cd=row["ntee_cd"],
        )

    for row in pub78.rows:
        r = merged[row["ein"]]
        r["ein"] = row["ein"]
        r["in_pub78"] = 1
        r["pub78_deductibility_code"] = row["deductibility_code"]
        if not r.get("name"):
            r["name"] = row["name"]
            r["city"] = r["city"] or row["city"]
            r["state"] = r["state"] or row["state"]

    # An organization can be revoked, reinstated, and revoked again. 19,136 EINs carry more
    # than one row in the 2026-08-11 file. Current status comes from the row with the LATEST
    # revocation date — never from file order, which is not guaranteed and would silently
    # invert the answer for those organizations if upstream ever re-sorted the file.
    #
    # Example, EIN 00-1037180:
    #     revoked 2013-06-15, reinstated 2013-06-15   <- history
    #     revoked 2017-06-15, not reinstated          <- current status: revoked
    latest_revocation: dict[str, dict] = {}
    for row in revocation.rows:
        existing = latest_revocation.get(row["ein"])
        if existing is None or _revocation_sort_key(row) > _revocation_sort_key(existing):
            latest_revocation[row["ein"]] = row

    for ein, row in latest_revocation.items():
        r = merged[ein]
        r["ein"] = ein
        r["in_revocation"] = 1
        r["revocation_date"] = _iso(row["revocation_date"])
        r["revocation_posting_date"] = _iso(row["revocation_posting_date"])
        r["reinstatement_date"] = _iso(row["reinstatement_date"])
        if not r.get("name"):
            r["name"] = row["name"]
            r["city"] = r["city"] or row["city"]
            r["state"] = r["state"] or row["state"]

    for row in epostcard.rows:
        r = merged[row["ein"]]
        r["ein"] = row["ein"]
        r["in_epostcard"] = 1
        r["epostcard_tax_year"] = row["tax_year"]
        r["epostcard_period_end"] = _iso(row["tax_period_end"])
        if not r.get("name"):
            r["name"] = row["name"]

    return dict(merged)


def shard_key(ein: str, *, digits: int = 2) -> str:
    return ein[:digits]


def plan_shards(eins: Iterable[str]) -> dict[str, list[str]]:
    """Group EINs by two-digit prefix, splitting oversized prefixes by the third digit.

    Splitting is decided on row count as a proxy for compressed size, then the caller
    verifies real byte sizes after compression. A three-digit shard is recorded in the
    manifest alongside two-digit ones and the client resolves the most specific available.
    """
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for ein in eins:
        by_prefix[shard_key(ein)].append(ein)

    # Rows per megabyte is roughly stable across prefixes because the schema is fixed, so
    # a row-count ceiling is a good enough proxy to decide splits before compressing.
    max_rows = 60_000
    planned: dict[str, list[str]] = {}
    for prefix, members in by_prefix.items():
        if len(members) <= max_rows:
            planned[prefix] = members
            continue
        for ein in members:
            planned.setdefault(shard_key(ein, digits=3), []).append(ein)
    return planned


def write_shard(path: Path, rows: list[dict], vintages: list[DatasetVintage]) -> None:
    """Write one standalone SQLite shard. Overwrites any existing file at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        placeholders = ",".join("?" for _ in _ORG_COLUMNS)
        conn.executemany(
            f"INSERT INTO organization ({','.join(_ORG_COLUMNS)}) VALUES ({placeholders})",
            [tuple(row.get(c) for c in _ORG_COLUMNS) for row in rows],
        )
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [(f"vintage.{v.dataset}", v.published.isoformat()) for v in vintages]
            + [(f"source_url.{v.dataset}", v.source_url) for v in vintages],
        )
        conn.commit()
        # Deterministic byte output for a given input, so a rebuild from the same sources
        # produces the same checksum and the manifest is meaningful.
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()


def compress(src: Path, dest: Path, *, level: int = 19) -> tuple[int, str]:
    """Compress ``src`` to ``dest`` with zstandard. Returns (bytes, sha256) of the result."""
    compressor = zstandard.ZstdCompressor(level=level)
    raw = src.read_bytes()
    blob = compressor.compress(raw)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    return len(blob), hashlib.sha256(blob).hexdigest()


def build_index(
    *,
    merged: dict[str, dict],
    vintages: list[DatasetVintage],
    out_dir: Path,
    vintage: str,
    built_at: datetime,
) -> dict[str, Any]:
    """Build every shard and the manifest. Returns the manifest as a dict.

    The manifest is written by the caller, after any smoke test, because writing it is the
    commit point.
    """
    plan = plan_shards(merged.keys())
    target = out_dir / vintage
    target.mkdir(parents=True, exist_ok=True)

    shards = []
    for prefix in sorted(plan):
        members = plan[prefix]
        rows = [merged[e] for e in sorted(members)]
        raw_path = target / f"shard-{prefix}.sqlite"
        write_shard(raw_path, rows, vintages)
        comp_path = target / f"shard-{prefix}.sqlite.zst"
        size, digest = compress(raw_path, comp_path)
        raw_path.unlink()
        shards.append(
            {
                "prefix": prefix,
                "file": comp_path.name,
                "bytes": size,
                "sha256": digest,
                "rows": len(rows),
            }
        )

    return {
        "manifest_version": MANIFEST_VERSION,
        "vintage": vintage,
        "built_at": built_at.isoformat(),
        "datasets": [v.to_dict() for v in vintages],
        "shards": shards,
    }


def write_manifest(manifest: dict[str, Any], out_dir: Path) -> Path:
    """Write manifest.json. This is the commit point — do it last."""
    path = out_dir / manifest["vintage"] / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
