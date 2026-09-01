"""Plain-English explainers, one per check id.

Served by ``grantcheck explain <check_id>`` and by the MCP ``explain_check`` tool. They are
Markdown files rather than strings in code so that a contributor who writes well but does
not write Python can improve them.
"""

from __future__ import annotations

from pathlib import Path

DIRECTORY = Path(__file__).parent


def available() -> list[str]:
    """Check ids that have an explainer, sorted."""
    return sorted(p.stem for p in DIRECTORY.glob("*.md"))


def get(check_id: str) -> str | None:
    """Return the explainer for a check id, or None when there is not one."""
    path = DIRECTORY / f"{check_id}.md"
    if not path.is_file() or path.parent != DIRECTORY:
        return None
    return path.read_text(encoding="utf-8")
