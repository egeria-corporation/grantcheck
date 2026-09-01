"""How close is this organization to automatic revocation?

Revocation is not a judgment call. It happens on a three-year counter: three consecutive
years without filing a 990, 990-EZ, or 990-N and the exemption is gone by operation of law.
Nobody publishes the distance to that cliff, which is what makes this the most useful line
in the report.

It is also the line most capable of doing harm, so three guards apply before any number is
computed:

1. **Organizations with no filing requirement are never flagged.** Churches, religious
   organizations, state instrumentalities, and code-00 organizations are 433,337 of the
   501(c)(3) universe — 22%. They cannot be delinquent because they were never due.
2. **Group subordinates are never flagged.** They are covered by the central organization's
   group return and frequently have no filings of their own.
3. **The Business Master File fallback can never produce a failure.** ``TAX_PERIOD`` is a
   processed-return period that lags actual filing by up to a year, so a count derived from
   it can be a year or more too high. Reporting that as delinquency would tell an
   organization that filed on time it is about to lose its exemption.
"""

from __future__ import annotations

from datetime import date

from grantcheck.checks import CheckContext
from grantcheck.checks.most_recent_filing import (
    exempt_from_filing,
    resolve_evidence,
)
from grantcheck.checks.pub78 import is_covered_by_group_ruling
from grantcheck.models import Check

LABEL = "Years since filing"
GROUP = "filing_health"

REVOCATION_THRESHOLD_YEARS = 3

_CLIFF = (
    "Automatic revocation triggers after three consecutive years without filing a Form 990, "
    "990-EZ, or 990-N."
)


def years_since(period_end: date, today: date) -> int:
    """Whole years elapsed since a tax period ended, floored at zero."""
    years = today.year - period_end.year
    if (today.month, today.day) < (period_end.month, period_end.day):
        years -= 1
    return max(0, years)


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("epostcard") or ctx.vintage("bmf")

    reason = exempt_from_filing(ctx)
    if reason:
        return Check(
            id="filing_recency",
            label=LABEL,
            group=GROUP,
            status="not_applicable",
            blocking=False,
            value="No annual return required",
            detail=(
                f"The Business Master File records this organization as {reason}, so the "
                "three-year automatic revocation counter does not apply."
            ),
            vintage=ctx.vintage("bmf"),
        )

    if is_covered_by_group_ruling(ctx):
        group = (ctx.value("group_exemption") or "").strip()
        return Check(
            id="filing_recency",
            label=LABEL,
            group=GROUP,
            status="not_applicable",
            blocking=False,
            value="Covered by a group return",
            detail=(
                f"This organization is a subordinate under group exemption number {group}. "
                "Subordinates are commonly included in the central organization's group "
                "return and have no filings of their own, so an absent filing history here "
                "is expected and does not indicate delinquency."
            ),
            vintage=ctx.vintage("bmf"),
        )

    evidence = resolve_evidence(ctx)
    if evidence.period_end is None:
        return Check(
            id="filing_recency",
            label=LABEL,
            group=GROUP,
            status="unknown",
            blocking=False,
            value=None,
            detail=(
                "No filing period is on record in the datasets this tool publishes, so the "
                f"distance to automatic revocation cannot be computed. {_CLIFF} Check the "
                "IRS Tax Exempt Organization Search directly."
            ),
            vintage=vintage,
        )

    years = years_since(evidence.period_end, ctx.today)

    if not evidence.authoritative:
        # BMF fallback. Report the number, cap the severity at a warning, and say plainly
        # why it cannot be trusted as a delinquency finding.
        status = "warn" if years >= 2 else "pass"
        return Check(
            id="filing_recency",
            label=LABEL,
            group=GROUP,
            status=status,
            blocking=False,
            value=f"{years} (from the most recent processed return)",
            detail=(
                f"Roughly {years} year(s) since the end of the most recent tax period the "
                "IRS has processed. This comes from the Business Master File, which records "
                "a processing period rather than a filing date and can lag actual filing by "
                f"more than a year, so treat it as approximate. {_CLIFF} Confirm against the "
                "IRS Tax Exempt Organization Search before acting on it."
            ),
            vintage=ctx.vintage("bmf"),
        )

    if years >= REVOCATION_THRESHOLD_YEARS:
        return Check(
            id="filing_recency",
            label=LABEL,
            group=GROUP,
            # A non-blocking failure. It reports a serious risk, but the mechanical hard
            # stop is the revocation itself, which auto_revocation reports.
            status="fail",
            blocking=False,
            value=str(years),
            detail=(
                f"{years} years since the most recent filing on record ({evidence.label}). "
                f"{_CLIFF} An organization at or past three years may already be on the "
                "next revocation posting. Filing the missing returns is the immediate "
                "action."
            ),
            vintage=ctx.vintage("epostcard"),
        )

    if years == 2:
        return Check(
            id="filing_recency",
            label=LABEL,
            group=GROUP,
            status="warn",
            blocking=False,
            value=str(years),
            detail=(
                f"Two years since the most recent filing on record ({evidence.label}). "
                f"{_CLIFF} One more missed year and the exemption goes automatically."
            ),
            vintage=ctx.vintage("epostcard"),
        )

    return Check(
        id="filing_recency",
        label=LABEL,
        group=GROUP,
        status="pass",
        blocking=False,
        value=str(years),
        detail=f"{years} year(s) since the most recent filing on record. {_CLIFF}",
        vintage=ctx.vintage("epostcard"),
    )
