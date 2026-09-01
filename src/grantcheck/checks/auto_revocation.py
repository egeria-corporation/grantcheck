"""Has the organization's exemption been automatically revoked, and was it reinstated?

Three consecutive years of not filing a 990, 990-EZ, or 990-N revokes the exemption
automatically, by operation of law, with no hearing and often no notice anyone at the
organization actually reads.

**The trap this check exists to avoid.** Presence on the Automatic Revocation List does not
mean currently revoked. Reinstated organizations stay on the list permanently with a
reinstatement date filled in — 181,259 of 1,246,171 rows in the 2026-08-11 vintage, roughly
one in seven. Reading membership alone as "revoked" would tell every one of them they cannot
receive federal money or deductible contributions. That is the single most damaging false
statement this tool could make.

A second, quieter trap: an organization can be revoked, reinstated, and revoked **again**.
19,136 EINs carry more than one row. The index resolves current status by latest revocation
date, so what arrives here is already the current event rather than whichever row happened
to come last in the file.
"""

from __future__ import annotations

from datetime import date

from grantcheck.checks import CheckContext
from grantcheck.models import Check

LABEL = "Auto-revocation"
GROUP = "tax_exemption"


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
    vintage = ctx.vintage("revocation")

    if not ctx.present_in("revocation"):
        return Check(
            id="auto_revocation",
            label=LABEL,
            group=GROUP,
            status="pass",
            blocking=True,
            value="No revocation on record",
            detail=("This EIN does not appear on the IRS Automatic Revocation of Exemption List."),
            vintage=vintage,
        )

    revoked = _as_date(ctx.value("revocation_date"))
    posted = _as_date(ctx.value("revocation_posting_date"))
    reinstated = _as_date(ctx.value("reinstatement_date"))

    # Reinstatement is frequently retroactive to the revocation date itself, so the test is
    # "on or after", never "strictly after". A strict comparison would report thousands of
    # reinstated organizations as still revoked.
    if reinstated and revoked and reinstated >= revoked:
        return Check(
            id="auto_revocation",
            label=LABEL,
            group=GROUP,
            status="pass",
            blocking=True,
            value=f"Revoked {revoked}, reinstated {reinstated}",
            detail=(
                f"The exemption was automatically revoked on {revoked} and reinstated on "
                f"{reinstated}. The organization stays on the published list permanently "
                "once it has been revoked, so its presence there is history rather than "
                "current status. It is in good standing on this measure."
            ),
            vintage=vintage,
        )

    if reinstated and revoked and reinstated < revoked:
        # A reinstatement predating the current revocation belongs to an earlier cycle.
        return Check(
            id="auto_revocation",
            label=LABEL,
            group=GROUP,
            status="fail",
            blocking=True,
            value=f"Revoked {revoked}",
            detail=(
                f"The exemption was automatically revoked on {revoked}. An earlier "
                f"reinstatement dated {reinstated} belongs to a previous revocation cycle "
                "and does not cure this one. Revoked organizations are ineligible for "
                "federal grants and cannot receive tax-deductible contributions until "
                "reinstated. Reinstatement is by Form 1023 or 1023-EZ, and retroactive "
                "reinstatement has deadlines — see IRS Revenue Procedure 2014-11."
            ),
            vintage=vintage,
        )

    if revoked:
        posted_text = f" and posted {posted}" if posted else ""
        return Check(
            id="auto_revocation",
            label=LABEL,
            group=GROUP,
            status="fail",
            blocking=True,
            value=f"Revoked {revoked}",
            detail=(
                f"The exemption was automatically revoked on {revoked}{posted_text} for "
                "three consecutive years of non-filing, and no reinstatement is recorded "
                "as of the date shown. Revoked organizations are ineligible for federal "
                "grants and cannot receive tax-deductible contributions until reinstated. "
                "Reinstatement is by Form 1023 or 1023-EZ, and retroactive reinstatement "
                "has deadlines — see IRS Revenue Procedure 2014-11."
            ),
            vintage=vintage,
        )

    return Check(
        id="auto_revocation",
        label=LABEL,
        group=GROUP,
        status="unknown",
        blocking=True,
        value="On the list, dates unreadable",
        detail=(
            "This EIN appears on the Automatic Revocation List but its revocation date "
            "could not be read, so current status cannot be determined here. Check the IRS "
            "Tax Exempt Organization Search directly before relying on this."
        ),
        vintage=vintage,
    )
