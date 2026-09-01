"""The Report data contract: serialization, round-trip, and readiness derivation."""

import json
from datetime import UTC, date, datetime

import pytest

from grantcheck.models import (
    DISCLOSURE,
    EXIT_ATTENTION,
    EXIT_BLOCKED,
    EXIT_NOT_FOUND,
    EXIT_OK,
    GROUPS,
    READINESS,
    SCHEMA_VERSION,
    STATUSES,
    Check,
    MatchConfidence,
    Opportunity,
    Organization,
    Report,
    Vintage,
    blocking_ids,
    derive_readiness,
)

BMF = Vintage(
    dataset="bmf",
    published=date(2026, 8, 11),
    source_url="https://www.irs.gov/pub/irs-soi/eo1.csv",
)


def a_check(
    id: str = "exempt_status",
    status: str = "pass",
    *,
    blocking: bool = True,
    group: str = "tax_exemption",
) -> Check:
    return Check(
        id=id,
        label=id.replace("_", " ").title(),
        group=group,
        status=status,
        blocking=blocking,
        value="Active",
        vintage=BMF,
    )


def a_report(**overrides: object) -> Report:
    base: dict[str, object] = {
        "ein": "27-0125367",
        "queried_at": datetime(2026, 9, 1, 12, 30, 45, tzinfo=UTC),
        "readiness": "ready",
        "organization": Organization(
            ein="27-0125367",
            name="CODE FOR AMERICA LABS INC",
            city="San Francisco",
            state="CA",
            ntee_code="W99",
            subsection="03",
            ruling_date="2010-02",
        ),
        "checks": [a_check()],
        "vintages": [BMF],
        "notes": ["Matched to SAM.gov by legal name and state, confidence 0.91"],
    }
    base.update(overrides)
    return Report(**base)  # type: ignore[arg-type]


class TestReadinessDerivation:
    def test_all_pass_is_ready(self) -> None:
        assert derive_readiness([a_check(), a_check("pub78_deductibility")]) == "ready"

    def test_blocking_failure_blocks(self) -> None:
        checks = [a_check(), a_check("sam_registration", "fail", blocking=True)]
        assert derive_readiness(checks) == "blocked"

    def test_warning_is_attention(self) -> None:
        checks = [a_check(), a_check("single_audit", "warn", blocking=False)]
        assert derive_readiness(checks) == "attention"

    def test_non_blocking_failure_is_attention_not_blocked(self) -> None:
        checks = [a_check(), a_check("filing_recency", "fail", blocking=False)]
        assert derive_readiness(checks) == "attention"

    def test_absent_ein_is_not_found(self) -> None:
        assert derive_readiness([], found=False) == "not_found"

    def test_not_found_wins_over_everything(self) -> None:
        checks = [a_check("sam_registration", "fail", blocking=True)]
        assert derive_readiness(checks, found=False) == "not_found"

    def test_blocked_wins_over_attention(self) -> None:
        checks = [
            a_check("single_audit", "warn", blocking=False),
            a_check("auto_revocation", "fail", blocking=True),
        ]
        assert derive_readiness(checks) == "blocked"

    def test_not_applicable_is_not_a_failure(self) -> None:
        # A group exemption subordinate is legitimately absent from Publication 78.
        checks = [a_check(), a_check("pub78_deductibility", "not_applicable", blocking=False)]
        assert derive_readiness(checks) == "ready"


class TestUnknownNeverBlocks:
    """The most damaging bug this tool could ship.

    An unchecked thing is not a failed thing. If `unknown` could produce `blocked`, the
    tool would tell a compliant organization it cannot apply for federal money because we
    failed to look something up.
    """

    def test_unknown_alone_is_ready(self) -> None:
        checks = [a_check(), a_check("sam_registration", "unknown", blocking=True)]
        assert derive_readiness(checks) == "ready"

    def test_all_unknown_is_ready_not_blocked(self) -> None:
        checks = [a_check(i, "unknown", blocking=True) for i in ("a", "b", "c")]
        assert derive_readiness(checks) == "ready"

    @pytest.mark.parametrize("blocking", [True, False])
    def test_unknown_never_blocks_at_any_blocking_setting(self, blocking: bool) -> None:
        assert derive_readiness([a_check("x", "unknown", blocking=blocking)]) == "ready"

    def test_unknown_does_not_appear_in_blocking_ids(self) -> None:
        checks = [a_check("sam_registration", "unknown", blocking=True)]
        assert blocking_ids(checks) == []

    def test_exhaustive_over_the_status_vocabulary(self) -> None:
        # Whatever statuses exist, only a blocking `fail` may produce `blocked`.
        for status in STATUSES:
            verdict = derive_readiness([a_check("x", status, blocking=True)])
            if status == "fail":
                assert verdict == "blocked"
            else:
                assert verdict != "blocked", f"status {status!r} produced blocked"


class TestBlockingIds:
    def test_lists_only_blocking_failures_in_order(self) -> None:
        checks = [
            a_check("auto_revocation", "fail", blocking=True),
            a_check("filing_recency", "fail", blocking=False),
            a_check("sam_registration", "fail", blocking=True),
        ]
        assert blocking_ids(checks) == ["auto_revocation", "sam_registration"]


class TestExitCodes:
    @pytest.mark.parametrize(
        ("readiness", "code"),
        [
            ("ready", EXIT_OK),
            ("blocked", EXIT_BLOCKED),
            ("attention", EXIT_ATTENTION),
            ("not_found", EXIT_NOT_FOUND),
        ],
    )
    def test_mapping(self, readiness: str, code: int) -> None:
        assert a_report(readiness=readiness).exit_code == code

    def test_every_readiness_value_has_a_code(self) -> None:
        for readiness in READINESS:
            assert a_report(readiness=readiness).exit_code is not None


class TestSerialization:
    def test_round_trip_is_lossless(self) -> None:
        original = a_report(
            opportunities=[
                Opportunity(
                    id="og-1",
                    title="Community Development Block Grant",
                    funder="HUD",
                    deadline=date(2026, 11, 30),
                    url="https://example.gov/cdbg",
                )
            ],
        )
        restored = Report.from_dict(json.loads(json.dumps(original.to_dict())))
        assert restored == original

    def test_round_trip_without_optional_sections(self) -> None:
        original = a_report(organization=None, opportunities=None, checks=[], vintages=[])
        restored = Report.from_dict(json.loads(json.dumps(original.to_dict())))
        assert restored == original
        assert restored.opportunities is None

    def test_is_json_serializable_without_a_custom_encoder(self) -> None:
        json.dumps(a_report().to_dict())

    def test_dates_are_iso_8601(self) -> None:
        d = a_report().to_dict()
        assert d["queried_at"] == "2026-09-01T12:30:45+00:00"
        assert d["vintages"][0]["published"] == "2026-08-11"

    def test_keys_are_snake_case(self) -> None:
        def walk(obj: object) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    assert k == k.lower(), f"{k!r} is not lowercase"
                    assert "-" not in k and " " not in k, f"{k!r} is not snake_case"
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(a_report().to_dict())

    def test_unknown_is_null_never_empty_string(self) -> None:
        # An empty string reads as "we looked and found nothing", which is a different
        # claim from "we did not look".
        check = Check(
            id="ntee", label="NTEE", group="filing_health", status="unknown", blocking=False
        )
        d = check.to_dict()
        assert d["value"] is None
        assert d["detail"] is None
        assert d["vintage"] is None


class TestContract:
    def test_schema_version_is_present_and_stable(self) -> None:
        assert a_report().to_dict()["schema_version"] == SCHEMA_VERSION == "1.0"

    def test_disclosure_is_carried_verbatim(self) -> None:
        assert a_report().to_dict()["disclosure"] == DISCLOSURE

    def test_disclosure_wording_is_exact(self) -> None:
        # Program conventions require this text verbatim. Changing it is a stop-and-ask.
        assert DISCLOSURE == (
            "This is informational only, derived from public data on the dates shown. It "
            "is not an eligibility determination, and not legal, tax, or accounting "
            "advice. Verify against the official source before relying on it."
        )

    def test_top_level_keys(self) -> None:
        assert set(a_report().to_dict()) == {
            "schema_version",
            "ein",
            "queried_at",
            "organization",
            "checks",
            "readiness",
            "blocking_check_ids",
            "opportunities",
            "vintages",
            "disclosure",
            "notes",
        }

    def test_check_groups_are_from_the_vocabulary(self) -> None:
        assert a_check().group in GROUPS


class TestImmutability:
    @pytest.mark.parametrize(
        "obj",
        [
            BMF,
            a_check(),
            Organization(ein="27-0125367", name="X"),
            MatchConfidence(score=0.91, method="name_state"),
        ],
    )
    def test_frozen(self, obj: object) -> None:
        with pytest.raises((AttributeError, TypeError)):
            obj.dataset = "changed"  # type: ignore[attr-defined]


class TestMatchConfidence:
    def test_round_trip(self) -> None:
        mc = MatchConfidence(
            score=0.91,
            method="name_state",
            matched_name="Code for America Labs, Inc.",
            note="Matched on legal name and state",
        )
        assert MatchConfidence.from_dict(json.loads(json.dumps(mc.to_dict()))) == mc

    def test_pinned_method_for_user_supplied_uei(self) -> None:
        assert MatchConfidence(score=1.0, method="pinned").method == "pinned"
