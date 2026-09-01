"""Does the organization have a Unique Entity ID?

The UEI replaced the DUNS number as the federal government's identifier for entities doing
business with it. No UEI means no SAM.gov registration, which means no federal award. It is
issued as part of registering, so an organization that has one has at least started.
"""

from __future__ import annotations

from grantcheck.checks import CheckContext
from grantcheck.checks.sam_registration import no_sam_data, unmatched_check
from grantcheck.models import Check

LABEL = "Unique Entity ID"
GROUP = "federal_registration"

UEI_LENGTH = 12


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("sam")
    if vintage is None and not (ctx.value("uei") or "").strip():
        return no_sam_data("uei", LABEL, ctx)

    uei = (ctx.value("uei") or "").strip()
    confidence = ctx.value("sam_match_confidence")

    if not uei and confidence is None and not ctx.value("sam_status"):
        return unmatched_check("uei", LABEL, ctx)

    if not uei:
        return Check(
            id="uei",
            label=LABEL,
            group=GROUP,
            status="fail",
            blocking=True,
            value="None on record",
            detail=(
                "No Unique Entity ID is on record. A UEI is issued through SAM.gov and is "
                "required before any federal grant application can be submitted. Requesting "
                "one is free at https://sam.gov and is the first step of registering."
            ),
            vintage=vintage,
        )

    return Check(
        id="uei",
        label=LABEL,
        group=GROUP,
        status="pass",
        blocking=True,
        value=uei,
        detail=(
            "A Unique Entity ID is on record. This is the identifier a federal application "
            "will ask for."
        ),
        vintage=vintage,
    )
