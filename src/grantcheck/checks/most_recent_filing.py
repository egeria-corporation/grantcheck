"""What is the most recent annual return on file, and how do we know?

**The trap this check exists to avoid.** The majority of exempt organizations file the Form
990-N e-Postcard, which does not appear in the Form 990 e-file XML index at all. Building
filing history from the e-file index alone would tell 1.5 million small nonprofits they had
never filed anything.

**The second trap.** ``TAX_PERIOD`` in the Business Master File is not a filing date. It is
the period of the most recent *processed* return, at month precision, lagging actual filing
by weeks to more than a year. It is usable only as an explicitly labelled fallback.

Evidence is therefore ranked, and the ranking is reported rather than hidden, because a
consultant needs to know whether a date is a filing or an inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from grantcheck.checks import CheckContext
from grantcheck.models import Check, Vintage

LABEL = "Most recent Form 990"
GROUP = "filing_health"

# FILING_REQ_CD values meaning the organization is not required to file an annual return.
# Verified against the 2026-08-10 Business Master File: 433,337 subsection-03 organizations
# carry one of these — 22% of the 501(c)(3) universe. Churches alone are 287,356. Flagging
# any of them as delinquent would be a false accusation at enormous scale.
NO_FILING_REQUIREMENT = {
    "00": "not required to file",
    "06": "a church, not required to file",
    "07": "a government 501(c)(1) organization",
    "13": "a religious organization not required to file",
    "14": "an instrumentality of a state or political subdivision",
}

# Covered by someone else's group return, so it does not file individually.
GROUP_RETURN = "03"


@dataclass(frozen=True)
class FilingEvidence:
    """What we know about the most recent filing, and how firmly."""

    period_end: date | None
    source: str  # 'epostcard' | 'bmf_tax_period' | 'none'
    authoritative: bool  # False for the BMF fallback, which is a processed-return period
    label: str


def _as_date(value: object) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _month_end(yyyy_mm: str) -> date | None:
    """Turn a ``YYYY-MM`` into the last day of that month.

    The BMF gives month precision. Taking the month end rather than the first is the
    conservative reading for recency: it makes the organization look *more* recently filed,
    so it can never manufacture a delinquency the data does not support.
    """
    try:
        year_text, month_text = str(yyyy_mm).split("-")
        year, month = int(year_text), int(month_text)
    except (ValueError, AttributeError):
        return None
    if not 1 <= month <= 12:
        return None
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def resolve_evidence(ctx: CheckContext) -> FilingEvidence:
    """Rank the available filing signals. Shared with the filing-recency check."""
    # The e-Postcard file carries an exact tax period end for the most recent 990-N. This
    # is a real filing record and is authoritative.
    period_end = _as_date(ctx.value("epostcard_period_end"))
    if ctx.present_in("epostcard") and period_end:
        year = ctx.value("epostcard_tax_year")
        label = f"Form 990-N (e-Postcard) for tax year {year}" if year else "Form 990-N"
        return FilingEvidence(period_end, "epostcard", True, label)

    # NOTE: the Form 990 e-file XML index is not yet part of the published index. Until it
    # is, a full 990 filer has no authoritative filing record here and falls through to the
    # labelled BMF fallback below. That is why the fallback exists and why it is labelled.
    tax_period = ctx.value("tax_period")
    if tax_period:
        end = _month_end(str(tax_period))
        if end:
            return FilingEvidence(
                end,
                "bmf_tax_period",
                False,
                f"most recent processed return, tax period ending {tax_period}",
            )

    return FilingEvidence(None, "none", False, "no filing on record")


def files_990pf(ctx: CheckContext) -> bool:
    """True when the organization files a Form 990-PF.

    Private foundations carry ``FILING_REQ_CD = 00``, which on its own reads as "no annual
    return required" — and 129,561 of them in the 2026-08-10 vintage also carry
    ``PF_FILING_REQ_CD = 1``, meaning they file a 990-PF and are subject to the same
    three-year automatic revocation counter as everyone else.

    Reading only ``FILING_REQ_CD`` would tell every one of those foundations it has no
    filing obligation. Only 4,507 organizations have both codes clear and are genuinely
    exempt from filing anything.
    """
    return (ctx.value("pf_filing_req_cd") or "").strip() not in ("", "0")


def exempt_from_filing(ctx: CheckContext) -> str | None:
    """Return a plain-English reason this organization need not file, or None."""
    if files_990pf(ctx):
        return None
    code = (ctx.value("filing_req_cd") or "").strip()
    if code in NO_FILING_REQUIREMENT:
        return NO_FILING_REQUIREMENT[code]
    if code == GROUP_RETURN:
        return "covered by a group return"
    return None


def check(ctx: CheckContext) -> Check:
    vintage: Vintage | None = ctx.vintage("epostcard") or ctx.vintage("bmf")
    evidence = resolve_evidence(ctx)

    if evidence.source == "epostcard":
        return Check(
            id="most_recent_filing",
            label=LABEL,
            group=GROUP,
            status="pass",
            blocking=False,
            value=f"Tax period ending {evidence.period_end}",
            detail=(
                f"Most recent annual return on record is a {evidence.label}. The Form 990-N "
                "e-Postcard is what most small organizations file, and it does not appear "
                "in the Form 990 e-file index."
            ),
            vintage=ctx.vintage("epostcard"),
        )

    if evidence.source == "bmf_tax_period":
        return Check(
            id="most_recent_filing",
            label=LABEL,
            group=GROUP,
            status="pass",
            blocking=False,
            value=f"Tax period ending {ctx.value('tax_period')}",
            detail=(
                "This is the period of the most recent return the IRS has processed, at "
                "month precision, taken from the Business Master File. It is not a filing "
                "date: processing lags filing by weeks to more than a year, so the actual "
                "return may be considerably more recent."
            ),
            vintage=ctx.vintage("bmf"),
        )

    reason = exempt_from_filing(ctx)
    if reason:
        return Check(
            id="most_recent_filing",
            label=LABEL,
            group=GROUP,
            status="not_applicable",
            blocking=False,
            value="No annual return required",
            detail=(
                f"No return is on record, and none is required: the Business Master File "
                f"records this organization as {reason}. An absent filing history is "
                "expected here and is not a problem."
            ),
            vintage=ctx.vintage("bmf"),
        )

    return Check(
        id="most_recent_filing",
        label=LABEL,
        group=GROUP,
        status="unknown",
        blocking=False,
        value=None,
        detail=(
            "No annual return is recorded in the datasets this tool publishes. That is not "
            "the same as never having filed — check the IRS Tax Exempt Organization Search "
            "directly before drawing a conclusion."
        ),
        vintage=vintage,
    )
