"""Markdown rendering — the same report as a document someone pastes into a memo.

Tables rather than glyph art, because this ends up in an email to a board chair or a
client, and a terminal check mark rendered in a mail client is a mystery box. The status is
spelled out in words for the same reason.
"""

from __future__ import annotations

from grantcheck.models import Report

GROUP_TITLES = {
    "tax_exemption": "Tax exemption",
    "filing_health": "Filing health",
    "federal_registration": "Federal registration",
    "audit_posture": "Audit posture",
}

STATUS_WORDS = {
    "pass": "OK",
    "warn": "Attention",
    "fail": "Problem",
    "unknown": "Not checked",
    "not_applicable": "Not applicable",
}

VERDICTS = {
    "ready": "Ready to apply",
    "attention": "Needs attention",
    "blocked": "Not ready",
    "not_found": "Not found",
}

DATASET_NAMES = {
    "bmf": "IRS EO Business Master File",
    "pub78": "IRS Publication 78",
    "revocation": "IRS Automatic Revocation List",
    "epostcard": "IRS Form 990-N e-Postcard file",
    "efile_index": "IRS Form 990 e-file index",
    "sam": "SAM.gov Entity Management",
    "fac": "Federal Audit Clearinghouse",
}


def _escape(text: str | None) -> str:
    """Keep a pipe in a value from breaking the table it sits in."""
    if not text:
        return ""
    return text.replace("|", "\\|").replace("\n", " ")


def render(report: Report) -> str:
    org = report.organization
    out: list[str] = []

    if org is not None:
        out.append(f"# {org.name.title()}")
        out.append("")
        identity = [f"**EIN {report.ein}**"]
        where = ", ".join(p for p in (org.city, org.state) if p)
        if where:
            identity.append(where)
        if org.ntee_code:
            identity.append(f"NTEE {org.ntee_code}")
        if org.subsection == "03":
            identity.append("501(c)(3)")
        out.append(" · ".join(identity))
    else:
        out.append(f"# EIN {report.ein}")

    out.append("")
    out.append(f"## {VERDICTS.get(report.readiness, report.readiness)}")
    out.append("")

    if report.readiness == "not_found":
        out.append(
            "This EIN is not in the published index. That is a real answer rather than an "
            "error: churches and their integrated auxiliaries, government instrumentalities, "
            "and organizations recognized very recently are legitimately absent, and some "
            "EIN prefixes have never been issued. Check the IRS Tax Exempt Organization "
            "Search directly before concluding anything."
        )
        out.append("")
        out.extend(_footer(report))
        return "\n".join(out) + "\n"

    if report.blocking_check_ids:
        n = len(report.blocking_check_ids)
        out.append(
            f"**{n} blocking item{'s' if n != 1 else ''}** — these mechanically prevent a "
            "federal application from being submitted."
        )
        out.append("")

    for group, title in GROUP_TITLES.items():
        members = [c for c in report.checks if c.group == group]
        if not members:
            continue
        out.append(f"### {title}")
        out.append("")
        out.append("| | Check | Finding | As of |")
        out.append("|---|---|---|---|")
        for check in members:
            word = STATUS_WORDS.get(check.status, check.status)
            vintage = check.vintage.published.isoformat() if check.vintage else ""
            out.append(f"| {word} | {_escape(check.label)} | {_escape(check.value)} | {vintage} |")
        out.append("")

        explained = [c for c in members if c.status in ("warn", "fail") and c.detail]
        for check in explained:
            out.append(f"**{_escape(check.label)}.** {check.detail}")
            out.append("")

    out.extend(_footer(report))
    return "\n".join(out) + "\n"


def _footer(report: Report) -> list[str]:
    out = ["---", ""]
    if report.vintages:
        out.append("**Sources.**")
        out.append("")
        for v in report.vintages:
            name = DATASET_NAMES.get(v.dataset, v.dataset)
            if v.source_url:
                out.append(f"- {name}, published {v.published} — <{v.source_url}>")
            else:
                out.append(f"- {name}, published {v.published}")
        out.append("")
    for note in report.notes:
        out.append(f"*{note}*")
        out.append("")
    out.append(f"> {report.disclosure}")
    return out
