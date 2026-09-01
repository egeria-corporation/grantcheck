"""When does the SAM.gov registration expire?

Registration lapses annually and renewal is **not** automatic. A registration in "Active"
status that expires in three weeks is not a pass — it is the thing that quietly disqualifies
an application submitted next month. The warning threshold is 60 days, which is roughly
four times the ten to fifteen business days a renewal takes to take effect.
"""

from __future__ import annotations

from datetime import date

from grantcheck.checks import CheckContext
from grantcheck.checks.sam_registration import no_sam_data, unmatched_check
from grantcheck.models import Check

LABEL = "Registration expires"
GROUP = "federal_registration"

# Renewal takes ten to fifteen business days to take effect. Warning at 60 days leaves room
# to notice, act, and still be active when the deadline arrives.
WARN_WITHIN_DAYS = 60


def _as_date(value: object) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("sam")
    if vintage is None:
        return no_sam_data("sam_expiration", LABEL, ctx)

    confidence = ctx.value("sam_match_confidence")
    expires = _as_date(ctx.value("sam_expiration"))

    if not ctx.value("sam_status") and confidence is None:
        return unmatched_check("sam_expiration", LABEL, ctx)

    if expires is None:
        return Check(
            id="sam_expiration",
            label=LABEL,
            group=GROUP,
            status="unknown",
            blocking=True,
            value=None,
            detail=(
                "The SAM.gov record does not carry an expiration date. Check the "
                "registration directly at https://sam.gov before relying on it."
            ),
            vintage=vintage,
        )

    days = (expires - ctx.today).days

    if days < 0:
        return Check(
            id="sam_expiration",
            label=LABEL,
            group=GROUP,
            status="fail",
            blocking=True,
            value=f"Expired {expires}",
            detail=(
                f"The registration expired on {expires}, {abs(days)} days ago. Federal "
                "applications cannot be submitted while a registration is expired. Renewal "
                "is free at https://sam.gov and takes ten to fifteen business days to take "
                "effect, so this needs starting before the next deadline rather than at it."
            ),
            vintage=vintage,
        )

    if days <= WARN_WITHIN_DAYS:
        return Check(
            id="sam_expiration",
            label=LABEL,
            group=GROUP,
            status="warn",
            blocking=False,
            value=f"{expires} ({days} days out)",
            detail=(
                f"The registration expires on {expires}, in {days} days. Renewal is not "
                "automatic and takes ten to fifteen business days to take effect, so a "
                "registration this close to expiry can lapse in the middle of an open "
                "application. Renew now rather than at the deadline."
            ),
            vintage=vintage,
        )

    return Check(
        id="sam_expiration",
        label=LABEL,
        group=GROUP,
        status="pass",
        blocking=True,
        value=f"{expires} ({days} days out)",
        detail=(
            f"The registration is current until {expires}. Renewal is annual and is not automatic."
        ),
        vintage=vintage,
    )
