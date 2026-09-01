"""JSON rendering. This is a public contract, not a debug dump.

The hosted site's ``/api/check/{ein}`` must return byte-identical output to this for the
same EIN at the same vintage, and CI asserts it. Consumers pin ``schema_version``.

Within a major version, changes are **additive only**: a new key is fine, a renamed or
removed one is not, and neither is changing what an existing key means. The committed
JSON Schema is the machine-readable statement of that, and a test validates real output
against it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from grantcheck.models import Report

SCHEMA_PATH = Path(__file__).parent.parent / "data" / "report-schema-1.0.json"


def render(report: Report, *, indent: int | None = 2) -> str:
    """Serialize a report. Keys are emitted in the order the schema documents them."""
    return json.dumps(report.to_dict(), indent=indent, ensure_ascii=False) + "\n"


def schema() -> dict[str, Any]:
    """The committed JSON Schema for the current major version."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
