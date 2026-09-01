"""Might this organization need a single audit?

**This is a screen, not an answer, and the wording has to keep saying so.** The honest
version is unsatisfying and there is a strong pull toward making it more definite. Resist
it. Getting this wrong in the confident direction tells an organization it does not need a
$15,000 audit that it does need, and they find out from a finding letter.

The threshold, verified 2026-09-01 against 2 CFR 200.501 and the Federal Audit Clearinghouse
help centre:

- **$750,000** for fiscal years beginning **before** 2024-10-01
- **$1,000,000** for fiscal years beginning **on or after** 2024-10-01

Three things that are easy to get wrong and each change the answer:

1. **It keys on the fiscal year BEGIN date**, not the end date and not the filing date. An
   organization whose year runs 2024-07-01 to 2025-06-30 is still on $750,000, despite
   filing well into the $1,000,000 era.
2. **It counts federal awards EXPENDED, not received.** Money drawn down this year against
   an award made two years ago counts this year. A grant received and unspent does not.
3. **It counts pass-through subawards too.** Federal money received from a state agency or a
   university is still federal money expended, and it is the part organizations most often
   leave out of the calculation.

Coverage is inherently partial and the output says so. Organizations below the threshold do
not file with the Federal Audit Clearinghouse at all, so absence from it is evidence of
nothing.
"""

from __future__ import annotations

from datetime import date

from grantcheck.checks import CheckContext
from grantcheck.models import Check

LABEL = "Single audit"
GROUP = "audit_posture"

THRESHOLD_BEFORE = 750_000
THRESHOLD_AFTER = 1_000_000

# 2 CFR 200.501, as revised by OMB in April 2024. Applies to non-federal entity fiscal years
# beginning on or after this date.
THRESHOLD_CHANGE_EFFECTIVE = date(2024, 10, 1)


def threshold_for(fiscal_year_begin: date) -> int:
    """The single audit threshold for a fiscal year beginning on the given date."""
    if fiscal_year_begin >= THRESHOLD_CHANGE_EFFECTIVE:
        return THRESHOLD_AFTER
    return THRESHOLD_BEFORE


def fiscal_year_begin(accounting_period_end_month: str, *, today: date) -> date | None:
    """Infer the start of the organization's current fiscal year from its year-end month.

    The Business Master File records ``ACCT_PD`` as the fiscal year-end month. A year ending
    in June begins in July; a year ending in December begins in January. Returns the start
    of the fiscal year that is currently underway on ``today``.
    """
    raw = (accounting_period_end_month or "").strip()
    if not raw.isdigit():
        return None
    end_month = int(raw)
    if not 1 <= end_month <= 12:
        return None

    begin_month = 1 if end_month == 12 else end_month + 1

    # The fiscal year underway today started either this calendar year or last.
    candidate = date(today.year, begin_month, 1)
    if candidate > today:
        candidate = date(today.year - 1, begin_month, 1)
    return candidate


def _money(amount: int) -> str:
    return f"${amount:,}"


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("bmf")
    begin = fiscal_year_begin(ctx.value("acct_pd") or "", today=ctx.today)

    # The federal-expenditure figure is not in the published index yet. It comes from the
    # government-grants field of the Form 990 e-file XML, and from Federal Audit
    # Clearinghouse filings where a key is present — neither of which this build carries.
    expended = ctx.value("federal_expenditures")

    if expended is None:
        if begin is None:
            return Check(
                id="single_audit",
                label=LABEL,
                group=GROUP,
                status="unknown",
                blocking=False,
                value="Cannot be screened",
                detail=(
                    "Whether a single audit is required depends on federal awards expended "
                    "during the fiscal year, which is not in this dataset. The threshold is "
                    f"{_money(THRESHOLD_AFTER)} for fiscal years beginning on or after "
                    f"{THRESHOLD_CHANGE_EFFECTIVE}, and {_money(THRESHOLD_BEFORE)} for years "
                    "beginning before it. Count everything federal, including subawards "
                    "passed through a state agency or a university, and count what was "
                    "spent rather than what was received. Your Schedule of Expenditures of "
                    "Federal Awards is where that number lives."
                ),
                vintage=vintage,
            )

        applicable = threshold_for(begin)
        if applicable == THRESHOLD_AFTER:
            change = (
                f"It rose from {_money(THRESHOLD_BEFORE)} for years beginning before "
                f"{THRESHOLD_CHANGE_EFFECTIVE}."
            )
        else:
            change = (
                f"It rises to {_money(THRESHOLD_AFTER)} for years beginning on or after "
                f"{THRESHOLD_CHANGE_EFFECTIVE}, so next year's number is probably different."
            )
        return Check(
            id="single_audit",
            label=LABEL,
            group=GROUP,
            status="unknown",
            blocking=False,
            value=f"Threshold {_money(applicable)} for the year beginning {begin}",
            detail=(
                f"Your current fiscal year began {begin}, so the threshold that applies to "
                f"it is {_money(applicable)} in federal awards expended. {change} "
                "This tool cannot tell you how much you expended — that figure is not in "
                "the public datasets it publishes. Count everything federal, including "
                "subawards passed through a state agency, a university, or a larger "
                "nonprofit, and count what was spent rather than what was received. Your "
                "Schedule of Expenditures of Federal Awards is where that number lives."
            ),
            vintage=vintage,
        )

    applicable = threshold_for(begin) if begin else THRESHOLD_AFTER
    amount = int(expended)

    if amount >= applicable:
        return Check(
            id="single_audit",
            label=LABEL,
            group=GROUP,
            # Never a failure. This is a screen against an incomplete figure, and a hard
            # finding drawn from it would be asserting something we cannot know.
            status="warn",
            blocking=False,
            value=f"{_money(amount)} reported, threshold {_money(applicable)}",
            detail=(
                f"Government grants of {_money(amount)} are reported on the most recent "
                f"return on file, which is above the {_money(applicable)} single audit "
                f"threshold for a fiscal year beginning {begin}. That figure is not the "
                "same as federal awards expended: it may include state and local money, "
                "and it may exclude federal subawards received through a pass-through "
                "entity. Go and look at your Schedule of Expenditures of Federal Awards, "
                "which is the number the requirement is actually measured against."
            ),
            vintage=vintage,
        )

    return Check(
        id="single_audit",
        label=LABEL,
        group=GROUP,
        status="pass",
        blocking=False,
        value=f"{_money(amount)} reported, below {_money(applicable)}",
        detail=(
            f"Government grants of {_money(amount)} are reported on the most recent return "
            f"on file, below the {_money(applicable)} threshold for a fiscal year beginning "
            f"{begin}. This is a screen rather than a determination: the reported figure "
            "may exclude federal subawards received through a state agency or a university, "
            "which count toward the threshold. Confirm against your Schedule of "
            "Expenditures of Federal Awards."
        ),
        vintage=vintage,
    )
