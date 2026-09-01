"""``build_report`` — the only thing the CLI and the MCP server ever call.

Both adapters call this function and hand the result to a renderer. Neither computes
anything, neither branches on a check status, and neither knows how a check works. That is
what makes it structurally impossible for the two surfaces to disagree, which matters
because the hosted site's JSON is asserted against the command-line tool's JSON in CI.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from grantcheck.checks import CheckContext, run_all
from grantcheck.ein import format_ein, normalize
from grantcheck.models import (
    Check,
    Organization,
    Report,
    Vintage,
    blocking_ids,
    derive_readiness,
)
from grantcheck.sources import opengrants
from grantcheck.sources.index import IndexClient, Manifest


def vintages_from_manifest(manifest: Manifest) -> dict[str, Vintage]:
    """Turn the manifest's dataset records into `Vintage` objects keyed by dataset."""
    out: dict[str, Vintage] = {}
    for entry in manifest.datasets:
        try:
            out[entry["dataset"]] = Vintage(
                dataset=entry["dataset"],
                published=date.fromisoformat(entry["published"]),
                source_url=entry.get("source_url", ""),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def organization_from_row(row: dict, ein: str) -> Organization:
    return Organization(
        ein=format_ein(ein),
        name=row.get("name") or "",
        sort_name=row.get("sort_name") or None,
        city=row.get("city") or None,
        state=row.get("state") or None,
        ntee_code=row.get("ntee_cd") or None,
        subsection=row.get("subsection") or None,
        classification=row.get("classification") or None,
        foundation_code=row.get("foundation") or None,
        group_exemption=row.get("group_exemption") or None,
        ruling_date=row.get("ruling") or None,
        uei=row.get("uei") or None,
    )


def build_report(
    ein: str,
    *,
    client: IndexClient | None = None,
    today: date | None = None,
    now: datetime | None = None,
    uei: str | None = None,
    enrich: bool = True,
) -> Report:
    """Produce the complete report for one EIN.

    Raises :class:`grantcheck.ein.InvalidEIN` for input that cannot be an EIN, and
    :class:`grantcheck.sources.index.IndexUnavailable` when the index cannot be reached and
    no usable cache exists. Everything else is reported inside the returned object rather
    than raised, because a partial answer with its gaps labelled is more useful than an
    error.
    """
    normalized = normalize(ein)
    client = client or IndexClient()
    manifest = client.manifest()
    row = client.lookup(normalized, manifest=manifest)

    if row is not None and uei:
        # A user-supplied UEI pins the SAM.gov match and skips inference entirely. This is
        # the escape hatch for every mismatch, and it has to override whatever the index
        # inferred rather than competing with it.
        row = dict(row)
        row["uei"] = uei.strip().upper()
        row["sam_match_confidence"] = 1.0
        row["sam_match_method"] = "pinned"
        row["sam_match_note"] = (
            f"SAM.gov entity pinned by the Unique Entity ID you supplied "
            f"({row['uei']}), so no name matching was performed."
        )

    ctx = CheckContext(
        ein=normalized,
        row=row,
        vintages=vintages_from_manifest(manifest),
        today=today or datetime.now(UTC).date(),
    )

    notes: list[str] = []
    match_note = ctx.value("sam_match_note")
    if match_note:
        notes.append(str(match_note))
    if manifest.from_cache:
        notes.append(
            "The dataset index could not be refreshed, so these vintages are from the "
            "local cache and may not be the newest published."
        )

    if row is None:
        # A well-formed EIN that is absent is a real answer, not an error. Churches,
        # government instrumentalities, and newly recognized organizations are legitimately
        # missing, and ten two-digit prefixes are never issued at all.
        checks: list[Check] = []
        return Report(
            ein=format_ein(normalized),
            queried_at=now or datetime.now(UTC),
            readiness="not_found",
            organization=None,
            checks=checks,
            blocking_check_ids=[],
            vintages=sorted(ctx.vintages.values(), key=lambda v: v.dataset),
            notes=notes,
        )

    checks = run_all(ctx)
    readiness = derive_readiness(checks, found=True)

    # Enrichment runs only on a clean report, which is the moment of maximum intent: the
    # tool has just said nothing mechanical is stopping this organization from applying.
    # It is additive and optional — every failure returns None and the report below is
    # byte-identical to one built with no key at all.
    opportunities = None
    if readiness == "ready" and enrich:
        enrichment = opengrants.match_opportunities(
            ein=normalized,
            state=row.get("state"),
            ntee_code=row.get("ntee_cd"),
        )
        if enrichment is not None:
            opportunities = enrichment.opportunities

    return Report(
        ein=format_ein(normalized),
        queried_at=now or datetime.now(UTC),
        readiness=readiness,
        organization=organization_from_row(row, normalized),
        checks=checks,
        blocking_check_ids=blocking_ids(checks),
        opportunities=opportunities,
        vintages=sorted(
            {c.vintage for c in checks if c.vintage is not None},
            key=lambda v: v.dataset,
        ),
        notes=notes,
    )
