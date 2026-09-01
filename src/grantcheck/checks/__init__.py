"""The check registry.

Each check is a pure function from a :class:`CheckContext` to a :class:`~grantcheck.models.Check`.
No check touches the network, reads the clock, or knows what a terminal is — everything it
needs arrives in the context, so a check is trivially testable and the CLI and the MCP
server necessarily produce identical results.

Order here is the order checks appear in output and in the JSON contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from grantcheck.models import Check, Vintage

CheckFn = Callable[["CheckContext"], Check]


@dataclass(frozen=True)
class CheckContext:
    """Everything a check is allowed to look at."""

    ein: str
    row: dict[str, Any] | None  # the index row; None when the EIN is not in the index
    vintages: dict[str, Vintage]
    today: date

    def vintage(self, dataset: str) -> Vintage | None:
        return self.vintages.get(dataset)

    def value(self, column: str) -> Any:
        return (self.row or {}).get(column)

    def present_in(self, dataset: str) -> bool:
        """Whether the organization appears in one of the four source datasets."""
        return bool(self.value(f"in_{dataset}"))


def _load_registry() -> list[tuple[str, CheckFn]]:
    from grantcheck.checks import (
        auto_revocation,
        exempt_status,
        filing_recency,
        most_recent_filing,
        ntee,
        organization_type,
        pub78,
    )

    return [
        ("exempt_status", exempt_status.check),
        ("pub78_deductibility", pub78.check),
        ("auto_revocation", auto_revocation.check),
        ("organization_type", organization_type.check),
        ("most_recent_filing", most_recent_filing.check),
        ("filing_recency", filing_recency.check),
        ("ntee", ntee.check),
    ]


def registry() -> list[tuple[str, CheckFn]]:
    return _load_registry()


def run_all(ctx: CheckContext) -> list[Check]:
    return [fn(ctx) for _, fn in registry()]
