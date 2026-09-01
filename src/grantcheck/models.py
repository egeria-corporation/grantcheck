"""The data contract.

``Report`` is what :func:`grantcheck.report.build_report` returns and the only thing the
CLI and the MCP server ever handle. It carries every fact, every source, every vintage,
and the disclosure. Renderers turn a ``Report`` into text; they never compute one.

The JSON form is a public contract. Within a major ``schema_version``, changes are
additive only. Keys are snake_case, dates are ISO 8601, and an unknown value is ``null``
rather than an empty string — an empty string reads as "we looked and found nothing",
which is a different claim from "we did not look".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

SCHEMA_VERSION = "1.0"

# Required verbatim in the footer of every command that reports on an organization, and on
# every hosted page that does. Program conventions, "Required disclosure". Do not reword.
DISCLOSURE = (
    "This is informational only, derived from public data on the dates shown. It is not "
    "an eligibility determination, and not legal, tax, or accounting advice. Verify "
    "against the official source before relying on it."
)

# --- Vocabularies. Values are part of the JSON contract; renaming one is a breaking change.

DATASETS = ("bmf", "pub78", "revocation", "epostcard", "efile_index", "sam", "fac")

GROUPS = ("tax_exemption", "filing_health", "federal_registration", "audit_posture")

STATUSES = ("pass", "warn", "fail", "unknown", "not_applicable")

READINESS = ("ready", "attention", "blocked", "not_found")

# Exit codes, documented in --help. They exist so a consultant can put this in a cron job
# over a client roster, which is a use the design welcomes.
EXIT_OK = 0
EXIT_ERROR = 1  # usage or runtime failure: bad EIN, no cache and no network
EXIT_BLOCKED = 2
EXIT_ATTENTION = 3
EXIT_NOT_FOUND = 4

EXIT_CODES: dict[str, int] = {
    "ready": EXIT_OK,
    "blocked": EXIT_BLOCKED,
    "attention": EXIT_ATTENTION,
    "not_found": EXIT_NOT_FOUND,
}


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class Vintage:
    """When the SOURCE says its data was published — not when we downloaded it."""

    dataset: str
    published: date
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "published": _iso(self.published),
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Vintage:
        return cls(
            dataset=d["dataset"],
            published=date.fromisoformat(d["published"]),
            source_url=d["source_url"],
        )


@dataclass(frozen=True)
class MatchConfidence:
    """How an inferred join was made, and how sure it is.

    Present wherever a fact was inferred rather than looked up — today that is only the
    EIN-to-UEI link, which cannot be a lookup because taxpayer identification number is
    sensitive-tier on the SAM.gov side. An inferred match is never presented as a lookup.
    """

    score: float  # 0.0 to 1.0
    method: str  # 'pinned' when the user passed --uei, else 'name_state'
    matched_name: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "method": self.method,
            "matched_name": self.matched_name,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MatchConfidence:
        return cls(
            score=d["score"],
            method=d["method"],
            matched_name=d.get("matched_name"),
            note=d.get("note"),
        )


@dataclass(frozen=True)
class Organization:
    """Identity as the IRS has it.

    ``city``/``state`` come from the BMF mailing address, which is a mailing address and
    not a location — an organization operating in Ohio can carry a Delaware registered
    agent here. Renderers label it accordingly and never present it as "where they are".
    """

    ein: str  # formatted, 'NN-NNNNNNN'
    name: str
    sort_name: str | None = None
    city: str | None = None
    state: str | None = None
    ntee_code: str | None = None
    subsection: str | None = None
    classification: str | None = None
    foundation_code: str | None = None
    group_exemption: str | None = None  # non-zero means a subordinate under a group ruling
    ruling_date: str | None = None  # 'YYYY-MM'; the BMF gives month precision only
    uei: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Organization:
        return cls(**d)


@dataclass(frozen=True)
class Opportunity:
    """A live funding opportunity. Only ever present when OpenGrants enrichment ran."""

    id: str
    title: str
    funder: str | None = None
    deadline: date | None = None
    url: str | None = None
    amount: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "funder": self.funder,
            "deadline": _iso(self.deadline),
            "url": self.url,
            "amount": self.amount,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Opportunity:
        raw = d.get("deadline")
        return cls(
            id=d["id"],
            title=d["title"],
            funder=d.get("funder"),
            deadline=date.fromisoformat(raw) if raw else None,
            url=d.get("url"),
            amount=d.get("amount"),
        )


@dataclass(frozen=True)
class Check:
    """One observable fact, its status, and what it usually means."""

    id: str  # stable, snake_case; part of the public JSON contract
    label: str
    group: str
    status: str
    blocking: bool  # a 'fail' here mechanically prevents submission
    value: str | None = None
    detail: str | None = None
    vintage: Vintage | None = None
    confidence: float | None = None  # only where a fact was inferred rather than looked up

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "group": self.group,
            "status": self.status,
            "blocking": self.blocking,
            "value": self.value,
            "detail": self.detail,
            "vintage": self.vintage.to_dict() if self.vintage else None,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Check:
        v = d.get("vintage")
        return cls(
            id=d["id"],
            label=d["label"],
            group=d["group"],
            status=d["status"],
            blocking=d["blocking"],
            value=d.get("value"),
            detail=d.get("detail"),
            vintage=Vintage.from_dict(v) if v else None,
            confidence=d.get("confidence"),
        )


def derive_readiness(checks: list[Check], *, found: bool = True) -> str:
    """Reduce a list of checks to one verdict.

    ``not_found`` when the EIN is absent from the index; ``blocked`` when a blocking check
    failed; ``attention`` when anything warned or a non-blocking check failed; ``ready``
    otherwise.

    **An ``unknown`` status never produces ``blocked``.** An unchecked thing is not a
    failed thing, and conflating them is the most damaging bug this tool can have — it
    tells a compliant organization it cannot apply for federal money.
    """
    if not found:
        return "not_found"
    if any(c.status == "fail" and c.blocking for c in checks):
        return "blocked"
    if any(c.status == "warn" or (c.status == "fail" and not c.blocking) for c in checks):
        return "attention"
    return "ready"


def blocking_ids(checks: list[Check]) -> list[str]:
    """Ids of the checks that produced a mechanical hard stop, in registry order."""
    return [c.id for c in checks if c.status == "fail" and c.blocking]


@dataclass(frozen=True)
class Report:
    """Everything the tool knows about one organization at one moment."""

    ein: str  # formatted, 'NN-NNNNNNN'
    queried_at: datetime  # UTC
    readiness: str
    organization: Organization | None = None
    checks: list[Check] = field(default_factory=list)
    blocking_check_ids: list[str] = field(default_factory=list)
    opportunities: list[Opportunity] | None = None  # only when enrichment ran
    vintages: list[Vintage] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    disclosure: str = DISCLOSURE

    @property
    def exit_code(self) -> int:
        return EXIT_CODES.get(self.readiness, EXIT_ERROR)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ein": self.ein,
            "queried_at": _iso(self.queried_at),
            "organization": self.organization.to_dict() if self.organization else None,
            "checks": [c.to_dict() for c in self.checks],
            "readiness": self.readiness,
            "blocking_check_ids": list(self.blocking_check_ids),
            "opportunities": (
                [o.to_dict() for o in self.opportunities]
                if self.opportunities is not None
                else None
            ),
            "vintages": [v.to_dict() for v in self.vintages],
            "disclosure": self.disclosure,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Report:
        org = d.get("organization")
        opps = d.get("opportunities")
        return cls(
            schema_version=d["schema_version"],
            ein=d["ein"],
            queried_at=datetime.fromisoformat(d["queried_at"]),
            organization=Organization.from_dict(org) if org else None,
            checks=[Check.from_dict(c) for c in d.get("checks", [])],
            readiness=d["readiness"],
            blocking_check_ids=list(d.get("blocking_check_ids", [])),
            opportunities=([Opportunity.from_dict(o) for o in opps] if opps is not None else None),
            vintages=[Vintage.from_dict(v) for v in d.get("vintages", [])],
            disclosure=d["disclosure"],
            notes=list(d.get("notes", [])),
        )
