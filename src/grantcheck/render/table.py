"""Terminal rendering. The default output.

Wraps at 80 columns and never assumes a wide terminal — this gets run over SSH and in a
split pane the night before a deadline. Colour only when the destination is a terminal and
``NO_COLOR`` is unset. Unicode glyphs degrade to ASCII when the encoding cannot carry them,
because a UnicodeEncodeError in place of a readiness report is a useless tool.
"""

from __future__ import annotations

import os
import sys
import textwrap
from collections.abc import Iterable

from grantcheck.models import Report

WIDTH = 79
INDENT = "  "
LABEL_WIDTH = 22

GROUP_TITLES = {
    "tax_exemption": "TAX EXEMPTION",
    "filing_health": "FILING HEALTH",
    "federal_registration": "FEDERAL REGISTRATION",
    "audit_posture": "AUDIT POSTURE",
}

GLYPHS = {
    "pass": "✔",  # heavy check mark
    "warn": "⚠",  # warning sign
    "fail": "✘",  # heavy ballot X
    "unknown": "?",
    "not_applicable": chr(0x2013),  # en dash
}

ASCII_GLYPHS = {
    "pass": "ok",
    "warn": "! ",
    "fail": "X ",
    "unknown": "? ",
    "not_applicable": "- ",
}

COLORS = {
    "pass": "\033[32m",
    "warn": "\033[33m",
    "fail": "\033[31m",
    "unknown": "\033[90m",
    "not_applicable": "\033[90m",
}
RESET = "\033[0m"
BOLD = "\033[1m"

VERDICTS = {
    "ready": "READY TO APPLY",
    "attention": "NEEDS ATTENTION",
    "blocked": "NOT READY",
    "not_found": "NOT FOUND",
}

# The NTEE code is promoted into the organization header rather than printed as its own row.
# It is still a full check in the JSON contract, which the hosted site and MCP server use.
PROMOTED_TO_HEADER = {"ntee"}


def supports_color(stream: object | None = None) -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def supports_unicode(stream: object | None = None) -> bool:
    stream = stream or sys.stdout
    encoding = getattr(stream, "encoding", None) or ""
    try:
        "✔⚠✘".encode(encoding or "ascii")
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _wrap(text: str, *, indent: str, width: int = WIDTH) -> list[str]:
    return textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent) or [
        indent.rstrip()
    ]


def render(
    report: Report,
    *,
    color: bool | None = None,
    unicode_glyphs: bool | None = None,
) -> str:
    """Render a report as the default terminal view."""
    use_color = supports_color() if color is None else color
    use_unicode = supports_unicode() if unicode_glyphs is None else unicode_glyphs
    glyphs = GLYPHS if use_unicode else ASCII_GLYPHS
    out: list[str] = [""]

    def paint(text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if use_color else text

    # -- Organization header ------------------------------------------------------------
    org = report.organization
    if org is not None:
        name = org.name.upper()
        ein_label = f"EIN {report.ein}"
        pad = max(1, WIDTH - len(INDENT) - len(name) - len(ein_label))
        if len(name) + pad + len(ein_label) > WIDTH - len(INDENT):
            out.append(f"{INDENT}{paint(name, BOLD)}")
            out.append(f"{INDENT}{ein_label}")
        else:
            out.append(f"{INDENT}{paint(name, BOLD)}{' ' * pad}{ein_label}")
        subtitle = _subtitle(report)
        if subtitle:
            out.append(f"{INDENT}{subtitle}")
    else:
        out.append(f"{INDENT}{paint(f'EIN {report.ein}', BOLD)}")

    # -- Verdict ------------------------------------------------------------------------
    out.append("")
    verdict = VERDICTS.get(report.readiness, report.readiness.upper())
    summary = _verdict_summary(report)
    verdict_color = {
        "ready": COLORS["pass"],
        "attention": COLORS["warn"],
        "blocked": COLORS["fail"],
        "not_found": COLORS["unknown"],
    }.get(report.readiness, "")
    if summary:
        pad = max(1, WIDTH - len(INDENT) - len(verdict) - len(summary))
        out.append(f"{INDENT}{paint(verdict, verdict_color)}{' ' * pad}{summary}")
    else:
        out.append(f"{INDENT}{paint(verdict, verdict_color)}")

    if report.readiness == "not_found":
        out.append("")
        for line in _wrap(_not_found_explanation(), indent=INDENT):
            out.append(line)
        out.extend(_footer(report, use_unicode=use_unicode))
        return "\n".join(out) + "\n"

    # -- Blocking failures first --------------------------------------------------------
    blocking = [c for c in report.checks if c.id in report.blocking_check_ids]
    if blocking:
        out.append("")
        for check in blocking:
            out.extend(_render_check(check, glyphs, paint, detail=True))

    # -- Grouped sections ---------------------------------------------------------------
    shown = [c for c in report.checks if c.id not in PROMOTED_TO_HEADER]
    for group, title in GROUP_TITLES.items():
        members = [c for c in shown if c.group == group]
        if not members:
            continue
        out.append("")
        out.append(f"{INDENT}{paint(title, BOLD)}")
        for check in members:
            needs_detail = check.status in ("warn", "fail") and check.id not in (
                report.blocking_check_ids
            )
            out.extend(_render_check(check, glyphs, paint, detail=needs_detail))

    out.extend(_footer(report, use_unicode=use_unicode))
    return "\n".join(out) + "\n"


def _subtitle(report: Report) -> str:
    org = report.organization
    if org is None:
        return ""
    bits: list[str] = []
    where = ", ".join(p for p in (org.city, org.state) if p)
    if where:
        bits.append(where)
    ntee = next((c for c in report.checks if c.id == "ntee"), None)
    if ntee is not None and ntee.value:
        bits.append(f"NTEE {ntee.value.split(' — ')[0]}")
    if org.subsection == "03":
        bits.append("501(c)(3)")
    return " · ".join(bits)


def _verdict_summary(report: Report) -> str:
    if report.readiness == "blocked":
        n = len(report.blocking_check_ids)
        return f"{n} blocking item{'s' if n != 1 else ''}"
    attention = [
        c for c in report.checks if c.status == "warn" or (c.status == "fail" and not c.blocking)
    ]
    if attention:
        n = len(attention)
        return f"{n} item{'s' if n != 1 else ''} need{'' if n != 1 else 's'} attention"

    # An unchecked thing must not block — but a verdict of READY TO APPLY printed over three
    # unknowns is its own kind of dishonest. The readiness value stays exactly as specified;
    # the summary line says what was not looked at.
    unchecked = [c for c in report.checks if c.status == "unknown"]
    if unchecked:
        n = len(unchecked)
        return f"{n} item{'s' if n != 1 else ''} could not be checked"
    return ""


def _render_check(check, glyphs: dict, paint, *, detail: bool) -> list[str]:
    glyph = glyphs.get(check.status, "?")
    colored = paint(glyph, COLORS.get(check.status, ""))
    label = check.label[:LABEL_WIDTH].ljust(LABEL_WIDTH)
    value = check.value or ""
    lines = [f"{INDENT}{colored}  {label} {value}".rstrip()]
    if detail and check.detail:
        lines.append("")
        for line in _wrap(check.detail, indent=INDENT + " " * 5):
            lines.append(line)
        lines.append("")
    return lines


def _not_found_explanation() -> str:
    return (
        "This EIN is not in the published index. That is a real answer rather than an "
        "error: churches and their integrated auxiliaries, government instrumentalities, "
        "and organizations recognized very recently are legitimately absent, and some EIN "
        "prefixes have never been issued at all. Check the IRS Tax Exempt Organization "
        "Search directly before concluding anything."
    )


def _footer(report: Report, *, use_unicode: bool) -> list[str]:
    # The box-drawing rule is not in cp1252, which is what a default Windows console uses.
    # Every non-ASCII character in the output has to degrade, not just the status glyphs —
    # a UnicodeEncodeError in place of a readiness report is a useless tool.
    rule = "─" if use_unicode else "-"
    out = ["", f"{INDENT}{rule * (WIDTH - len(INDENT))}"]

    if report.vintages:
        sources = "; ".join(f"{_dataset_name(v.dataset)} ({v.published})" for v in report.vintages)
        for line in _wrap(f"Sources: {sources}.", indent=INDENT):
            out.append(line)

    for note in report.notes:
        out.append("")
        for line in _wrap(note, indent=INDENT):
            out.append(line)

    out.append("")
    for line in _wrap(report.disclosure, indent=INDENT):
        out.append(line)
    return out


def _dataset_name(dataset: str) -> str:
    return {
        "bmf": "IRS EO Business Master File",
        "pub78": "IRS Publication 78",
        "revocation": "IRS Automatic Revocation List",
        "epostcard": "IRS Form 990-N e-Postcard file",
        "efile_index": "IRS Form 990 e-file index",
        "sam": "SAM.gov Entity Management",
        "fac": "Federal Audit Clearinghouse",
    }.get(dataset, dataset)


def render_lines(reports: Iterable[Report]) -> str:
    return "\n".join(render(r) for r in reports)
