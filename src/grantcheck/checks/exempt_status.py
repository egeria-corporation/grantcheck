"""Is the organization recognized as exempt under section 501(c)(3)?

Most federal programs restrict eligibility to organizations described in section 501(c)(3).
If the Business Master File does not show an unconditional exemption under subsection 03,
the applicant is not what the notice of funding opportunity says it must be.
"""

from __future__ import annotations

from grantcheck.checks import CheckContext
from grantcheck.models import Check

LABEL = "Exempt status"
GROUP = "tax_exemption"

# BMF STATUS 01 is unconditional exemption. Other values exist for conditional exemption and
# for organizations terminating private foundation status; those are reported as observed
# rather than judged.
UNCONDITIONAL = "01"
CHARITABLE = "03"


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("bmf")

    if not ctx.present_in("bmf"):
        # Absence from the BMF is not a failure. Churches are exempt without applying and
        # are largely absent, as are government instrumentalities and very recently
        # recognized organizations. Calling this a failure would accuse a compliant
        # organization of something the data does not say.
        return Check(
            id="exempt_status",
            label=LABEL,
            group=GROUP,
            status="unknown",
            blocking=True,
            value=None,
            detail=(
                "This EIN is not in the IRS Exempt Organizations Business Master File. "
                "Churches, their integrated auxiliaries, and government instrumentalities "
                "are exempt without applying and are frequently absent, as are "
                "organizations recognized very recently. Absence here is not evidence of a "
                "problem. Check the IRS Tax Exempt Organization Search directly."
            ),
            vintage=vintage,
        )

    subsection = (ctx.value("subsection") or "").strip()
    status = (ctx.value("exempt_status") or "").strip()
    ruling = ctx.value("ruling")

    if subsection == CHARITABLE and status == UNCONDITIONAL:
        detail = "Recognized under section 501(c)(3)."
        if ruling:
            detail = f"Recognized under section 501(c)(3), ruling dated {ruling}."
        return Check(
            id="exempt_status",
            label=LABEL,
            group=GROUP,
            status="pass",
            blocking=True,
            value="501(c)(3), unconditional exemption",
            detail=detail,
            vintage=vintage,
        )

    if subsection != CHARITABLE:
        value = "Not 501(c)(3)"
        if subsection.isdigit():
            value = f"501(c)({int(subsection)})"
        return Check(
            id="exempt_status",
            label=LABEL,
            group=GROUP,
            status="fail",
            blocking=True,
            value=value,
            detail=(
                f"The Business Master File records this organization under subsection "
                f"{subsection}, not 03. Most federal grant programs limit eligibility to "
                "organizations described in section 501(c)(3). Some programs do accept "
                "other subsections, so read the eligibility section of the notice of "
                "funding opportunity before ruling it out."
            ),
            vintage=vintage,
        )

    return Check(
        id="exempt_status",
        label=LABEL,
        group=GROUP,
        status="warn",
        blocking=False,
        value=f"501(c)(3), status code {status}",
        detail=(
            f"Recognized under section 501(c)(3), but the exemption status code is "
            f"{status} rather than 01 (unconditional exemption). Worth confirming against "
            "the IRS Tax Exempt Organization Search before applying."
        ),
        vintage=vintage,
    )
