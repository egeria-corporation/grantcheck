"""Is the organization listed in Publication 78 as eligible for deductible contributions?

**The trap this check exists to avoid.** A group exemption subordinate is legitimately
absent from Publication 78: the central organization is listed and the ruling covers its
subordinates. Reporting that absence as a problem tells a compliant organization it cannot
receive tax-deductible contributions, and it would do so for roughly 238,000 organizations.
"""

from __future__ import annotations

from grantcheck.checks import CheckContext
from grantcheck.models import Check

LABEL = "Pub 78 deductibility"
GROUP = "tax_exemption"

# Measured across every subsection-03 row in the 2026-08 vintage: AFFILIATION 9 and 7 are
# 0.0% listed in Publication 78, while 6 and 8 are ~99.5% listed. A central organization
# carries the group exemption number too, so GROUP alone is the wrong signal.
COVERED_BY_ANOTHERS_RULING = frozenset({"7", "9"})

CODE_MEANINGS = {
    "PC": "public charity",
    "PF": "private foundation",
    "POF": "private operating foundation",
    "SO": "supporting organization",
    "SOUNK": "supporting organization, type unspecified",
    "EO": "an organization other than a charity",
    "GROUP": "a group ruling",
    "FORGN": "a foreign organization",
    "UNKWN": "type not stated",
}


def is_covered_by_group_ruling(ctx: CheckContext) -> bool:
    """True when another organization's group ruling covers this one."""
    group = (ctx.value("group_exemption") or "").strip()
    if not group or set(group) == {"0"}:
        return False
    return (ctx.value("affiliation") or "").strip() in COVERED_BY_ANOTHERS_RULING


def check(ctx: CheckContext) -> Check:
    vintage = ctx.vintage("pub78")

    if ctx.present_in("pub78"):
        code = (ctx.value("pub78_deductibility_code") or "").strip()
        meaning = CODE_MEANINGS.get(code)
        value = f"Listed — {code}"
        if meaning:
            value = f"Listed — {code} ({meaning})"
        return Check(
            id="pub78_deductibility",
            label=LABEL,
            group=GROUP,
            status="pass",
            blocking=False,
            value=value,
            detail=(
                "Listed in IRS Publication 78, the roster of organizations eligible to "
                "receive tax-deductible charitable contributions."
            ),
            vintage=vintage,
        )

    if is_covered_by_group_ruling(ctx):
        group = (ctx.value("group_exemption") or "").strip()
        return Check(
            id="pub78_deductibility",
            label=LABEL,
            group=GROUP,
            status="not_applicable",
            blocking=False,
            value="Covered by a group ruling",
            detail=(
                f"This organization is a subordinate under group exemption number {group}, "
                "so it does not appear in Publication 78 in its own right — the central "
                "organization is listed and the ruling covers its subordinates. This is "
                "normal and is not a problem. A funder asking for proof of deductibility "
                "will want the central organization's group exemption letter."
            ),
            vintage=vintage,
        )

    if not ctx.present_in("bmf"):
        return Check(
            id="pub78_deductibility",
            label=LABEL,
            group=GROUP,
            status="unknown",
            blocking=False,
            value=None,
            detail=(
                "Not listed in Publication 78, and not in the Business Master File either, "
                "so there is nothing to interpret the absence against. Churches are the "
                "common case: they may receive deductible contributions without being "
                "listed."
            ),
            vintage=vintage,
        )

    return Check(
        id="pub78_deductibility",
        label=LABEL,
        group=GROUP,
        status="warn",
        blocking=False,
        value="Not listed",
        detail=(
            "Not listed in IRS Publication 78. For an organization that is not covered by a "
            "group ruling, this is worth explaining before a funder notices it. Common "
            "reasons are a recent recognition that has not propagated yet, a revoked "
            "exemption, or a church that is eligible without being listed. It is not by "
            "itself a disqualification."
        ),
        vintage=vintage,
    )
