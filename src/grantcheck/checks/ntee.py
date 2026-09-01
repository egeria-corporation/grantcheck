"""What National Taxonomy of Exempt Entities code does the IRS have on file?

Purely informational. Program officers and eligibility filters both use it, and it is often
missing or wrong on the IRS side — which is itself worth knowing, because correcting it is
something an organization can do.

Absence is ``unknown`` and never a failure. The terminal renderer promotes this to the
organization header line rather than printing it as a row; it remains a full check in the
JSON contract either way, because the hosted site and the MCP server consume that.
"""

from __future__ import annotations

from grantcheck.checks import CheckContext
from grantcheck.models import Check

LABEL = "NTEE classification"
GROUP = "filing_health"

# The major group letter. The three-digit remainder is a finer classification that this tool
# reports verbatim rather than interpreting.
MAJOR_GROUPS = {
    "A": "Arts, Culture and Humanities",
    "B": "Education",
    "C": "Environment",
    "D": "Animal-Related",
    "E": "Health Care",
    "F": "Mental Health and Crisis Intervention",
    "G": "Voluntary Health Associations and Medical Disciplines",
    "H": "Medical Research",
    "I": "Crime and Legal-Related",
    "J": "Employment",
    "K": "Food, Agriculture and Nutrition",
    "L": "Housing and Shelter",
    "M": "Public Safety, Disaster Preparedness and Relief",
    "N": "Recreation and Sports",
    "O": "Youth Development",
    "P": "Human Services",
    "Q": "International, Foreign Affairs and National Security",
    "R": "Civil Rights, Social Action and Advocacy",
    "S": "Community Improvement and Capacity Building",
    "T": "Philanthropy, Voluntarism and Grantmaking Foundations",
    "U": "Science and Technology",
    "V": "Social Science",
    "W": "Public and Societal Benefit",
    "X": "Religion-Related",
    "Y": "Mutual and Membership Benefit",
    "Z": "Unknown",
}


def describe(code: str) -> str | None:
    code = (code or "").strip().upper()
    if not code:
        return None
    return MAJOR_GROUPS.get(code[0])


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("bmf")
    code = (ctx.value("ntee_cd") or "").strip()

    if not code:
        return Check(
            id="ntee",
            label=LABEL,
            group=GROUP,
            status="unknown",
            blocking=False,
            value=None,
            detail=(
                "The Business Master File does not record an NTEE code for this "
                "organization. This is common and is not a problem in itself, but it can "
                "affect how the organization surfaces in funder search tools that filter on "
                "it. An organization can ask the IRS to correct or add its classification."
            ),
            vintage=vintage,
        )

    described = describe(code)
    value = code if not described else f"{code} — {described}"
    return Check(
        id="ntee",
        label=LABEL,
        group=GROUP,
        status="pass",
        blocking=False,
        value=value,
        detail=(
            f"The IRS records this organization under NTEE code {code}. NTEE codes are "
            "self-reported at application and are frequently out of date, so it is worth "
            "confirming it still describes the work."
        ),
        vintage=vintage,
    )
