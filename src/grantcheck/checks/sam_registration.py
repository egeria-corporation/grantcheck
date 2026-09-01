"""Is the organization's SAM.gov registration active?

An active registration in the System for Award Management is a hard gate on every federal
grant and contract. Registrations lapse annually and renewal is not automatic, which makes
this the single most common avoidable disqualification in the federal system.

Three distinctions this check refuses to collapse:

- **"Not matched" is not "not registered".** The EIN-to-UEI link is inferred, so a failure
  to identify the organization is a gap in our inference, not a finding about them. It
  reports ``unknown`` and tells the reader to pin the match with ``--uei``.
- **"Expired" is not "not found".** They are different failures with different remedies —
  one is a renewal, the other is a first registration that takes considerably longer.
- **Registration purpose matters.** An entity registered for contracts only is active and
  still cannot receive a grant. That is reported rather than glossed.
"""

from __future__ import annotations

from grantcheck.checks import CheckContext
from grantcheck.models import Check

LABEL = "SAM.gov registration"
GROUP = "federal_registration"

# SAM.gov registration purpose. A grant-seeking organization needs the assistance purpose;
# "all awards" covers it, "federal contracts only" does not.
ASSISTANCE_PURPOSES = {"Z2", "Z5", "ALL_AWARDS", "FINANCIAL_ASSISTANCE_AWARDS_ONLY"}


def no_sam_data(check_id: str, label: str, ctx: CheckContext) -> Check:
    """The index build carries no SAM.gov data at all.

    Distinct from every other outcome, including a pinned UEI: knowing *which* registration
    to look at does not help when there is nothing to look at. Reporting "no registration
    found" here would be a finding about the organization drawn from our own missing data,
    which is the worst kind of wrong answer this tool could produce.
    """
    return Check(
        id=check_id,
        label=label,
        group=GROUP,
        status="unknown",
        blocking=True,
        value="Not checked",
        detail=(
            "This index build does not include SAM.gov data, so registration status, "
            "expiration, and Unique Entity ID were not checked. Nothing here says anything "
            "about the organization's registration — check it directly at https://sam.gov."
        ),
        vintage=None,
    )


def unmatched_check(check_id: str, label: str, ctx: CheckContext) -> Check:
    """The shared `unknown` result used by all three SAM checks below the confidence floor.

    Deliberately one function, so the three checks cannot drift into saying three different
    things about the same underlying situation — and so a reader does not see the same
    problem reported three times as three separate failures.
    """
    note = ctx.value("sam_match_note") or (
        "Could not confidently match this EIN to a SAM.gov entity by legal name and state."
    )
    return Check(
        id=check_id,
        label=label,
        group=GROUP,
        status="unknown",
        blocking=True,
        value="Could not identify the registration",
        detail=(
            f"{note} This is a limitation of the join, not a finding about the "
            "organization: the IRS identifies organizations by EIN and SAM.gov's public "
            "tier cannot be searched by one, so the link has to be inferred from name and "
            "state. Re-run with --uei to pin the registration and get a definite answer."
        ),
        vintage=ctx.vintage("sam"),
    )


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("sam")
    if vintage is None:
        return no_sam_data("sam_registration", LABEL, ctx)

    status = (ctx.value("sam_status") or "").strip()
    confidence = ctx.value("sam_match_confidence")

    if not status and confidence is None:
        return unmatched_check("sam_registration", LABEL, ctx)

    if not status:
        return Check(
            id="sam_registration",
            label=LABEL,
            group=GROUP,
            status="fail",
            blocking=True,
            value="No registration found",
            detail=(
                "No SAM.gov entity registration was found for this organization. An active "
                "registration is required before a federal grant application can be "
                "submitted. Registering is free at https://sam.gov and takes considerably "
                "longer than renewing — allow several weeks, and start with the Unique "
                "Entity ID request. This is a different problem from an expired "
                "registration, which is only a renewal."
            ),
            vintage=vintage,
        )

    purpose = (ctx.value("sam_purpose") or "").strip()
    normalized = status.upper()

    if normalized == "ACTIVE":
        if purpose and purpose.upper() not in ASSISTANCE_PURPOSES:
            return Check(
                id="sam_registration",
                label=LABEL,
                group=GROUP,
                status="warn",
                blocking=False,
                value=f"Active, {purpose}",
                detail=(
                    f"The registration is active, but its purpose is recorded as {purpose}. "
                    "An entity registered for federal contracts only cannot receive a "
                    "grant or cooperative agreement. Updating the registration purpose to "
                    "include financial assistance is done in SAM.gov and does not require "
                    "starting over."
                ),
                vintage=vintage,
            )
        value = "Active" if not purpose else f"Active, {purpose}"
        return Check(
            id="sam_registration",
            label=LABEL,
            group=GROUP,
            status="pass",
            blocking=True,
            value=value,
            detail="The SAM.gov entity registration is active.",
            vintage=vintage,
        )

    return Check(
        id="sam_registration",
        label=LABEL,
        group=GROUP,
        status="fail",
        blocking=True,
        value=status,
        detail=(
            f"The SAM.gov entity registration is recorded as {status}. Federal "
            "applications cannot be submitted while a registration is not active. "
            "Renewal is free and is done at https://sam.gov; allow ten to fifteen "
            "business days for it to take effect."
        ),
        vintage=vintage,
    )
