"""Is this a private foundation?

Private foundations are excluded from the eligibility language of most federal grant
programs, which surprises more people than it should. This is a warning rather than a
failure: it is a fact about the organization, and whether it disqualifies depends on the
notice of funding opportunity.
"""

from __future__ import annotations

from grantcheck.checks import CheckContext
from grantcheck.models import Check

LABEL = "Organization type"
GROUP = "tax_exemption"

# BMF FOUNDATION codes. Sourced from the published EO BMF data dictionary rather than
# written from memory — this is exactly the sort of table that is 90% right and wrong in the
# one row that matters.
PRIVATE_FOUNDATION_CODES = {
    "02": "private operating foundation, exempt operating foundation",
    "03": "private operating foundation (other)",
    "04": "private non-operating foundation",
}

PUBLIC_CHARITY_CODES = {
    "09": "suborganization of a public charity",
    "10": "church",
    "11": "school",
    "12": "hospital or medical research organization",
    "13": "organization supported by a governmental unit",
    "14": "publicly supported organization",
    "15": "publicly supported organization",
    "16": "supporting organization, section 509(a)(3)",
    "17": "public safety testing organization",
    "18": "supporting organization, section 509(a)(3)",
    "21": "509(a)(3) supporting organization, type unspecified",
}


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("bmf")
    code = (ctx.value("foundation") or "").strip()

    if not ctx.present_in("bmf") or not code:
        return Check(
            id="organization_type",
            label=LABEL,
            group=GROUP,
            status="unknown",
            blocking=False,
            value=None,
            detail=(
                "The Business Master File does not record a foundation classification for "
                "this EIN, so whether it is a private foundation cannot be determined here."
            ),
            vintage=vintage,
        )

    if code in PRIVATE_FOUNDATION_CODES:
        return Check(
            id="organization_type",
            label=LABEL,
            group=GROUP,
            status="warn",
            blocking=False,
            value=f"Private foundation ({PRIVATE_FOUNDATION_CODES[code]})",
            detail=(
                "Classified as a private foundation. Most federal grant programs restrict "
                "eligibility to public charities and exclude private foundations, so this "
                "is worth settling before investing time in an application. It is a "
                "classification, not a disqualification — check the eligibility section of "
                "the specific notice of funding opportunity."
            ),
            vintage=vintage,
        )

    described = PUBLIC_CHARITY_CODES.get(code)
    value = "Public charity, not a private foundation"
    if described:
        value = f"Public charity — {described}"
    return Check(
        id="organization_type",
        label=LABEL,
        group=GROUP,
        status="pass",
        blocking=False,
        value=value,
        detail=(
            "Not classified as a private foundation, so the exclusion most federal "
            "programs apply to private foundations does not bite here."
        ),
        vintage=vintage,
    )
