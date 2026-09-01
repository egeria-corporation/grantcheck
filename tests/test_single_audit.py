"""The single audit screen, and the threshold rule that decides it.

Verified 2026-09-01 against 2 CFR 200.501 and the Federal Audit Clearinghouse help centre:
$750,000 for fiscal years beginning before 2024-10-01, $1,000,000 on or after. The rule
keys on the fiscal year BEGIN date, which is the part most easily got wrong.
"""

from __future__ import annotations

from datetime import date

import pytest

from grantcheck.checks import CheckContext
from grantcheck.checks.single_audit import (
    THRESHOLD_AFTER,
    THRESHOLD_BEFORE,
    THRESHOLD_CHANGE_EFFECTIVE,
    check,
    fiscal_year_begin,
    threshold_for,
)
from grantcheck.models import Vintage

TODAY = date(2026, 9, 1)
BMF = Vintage("bmf", date(2026, 8, 10), "https://www.irs.gov/pub/irs-soi/eo1.csv")


def ctx(**row: object) -> CheckContext:
    base: dict[str, object] = {"in_bmf": 1}
    base.update(row)
    return CheckContext(ein="271067272", row=base, vintages={"bmf": BMF}, today=TODAY)


class TestThresholdRule:
    def test_the_two_amounts(self) -> None:
        assert THRESHOLD_BEFORE == 750_000
        assert THRESHOLD_AFTER == 1_000_000

    def test_effective_date(self) -> None:
        assert THRESHOLD_CHANGE_EFFECTIVE.isoformat() == "2024-10-01"

    @pytest.mark.parametrize(
        ("begins", "expected"),
        [
            (date(2024, 9, 30), THRESHOLD_BEFORE),  # day before
            (date(2024, 10, 1), THRESHOLD_AFTER),  # the boundary itself is "on or after"
            (date(2024, 10, 2), THRESHOLD_AFTER),
            (date(2023, 1, 1), THRESHOLD_BEFORE),
            (date(2026, 1, 1), THRESHOLD_AFTER),
        ],
    )
    def test_boundary(self, begins: date, expected: int) -> None:
        assert threshold_for(begins) == expected

    def test_a_mid_year_filer_is_still_on_the_old_threshold(self) -> None:
        # Fiscal year 2024-07-01 to 2025-06-30: filed well into the $1M era, still $750k,
        # because the rule keys on when the year BEGAN.
        assert threshold_for(date(2024, 7, 1)) == THRESHOLD_BEFORE


class TestFiscalYearInference:
    @pytest.mark.parametrize(
        ("acct_pd", "expected_month"),
        [("12", 1), ("06", 7), ("09", 10), ("01", 2), ("03", 4)],
    )
    def test_year_begins_the_month_after_it_ends(self, acct_pd: str, expected_month: int) -> None:
        begin = fiscal_year_begin(acct_pd, today=TODAY)
        assert begin is not None
        assert begin.month == expected_month

    def test_the_year_underway_today_is_the_one_returned(self) -> None:
        # Today is 2026-09-01. A December year-end means the current year began 2026-01-01.
        assert fiscal_year_begin("12", today=TODAY) == date(2026, 1, 1)

    def test_a_year_that_has_not_started_yet_rolls_back(self) -> None:
        # An October year-end means the year begins in November. On 2026-09-01 the year
        # underway began 2025-11-01, not 2026-11-01, which is in the future.
        assert fiscal_year_begin("10", today=TODAY) == date(2025, 11, 1)

    @pytest.mark.parametrize("bad", ["", "  ", "00", "13", "xx", "1.5"])
    def test_unusable_values_return_none(self, bad: str) -> None:
        assert fiscal_year_begin(bad, today=TODAY) is None


class TestScreenNeverAsserts:
    """A screen, never an answer. The pull toward being definite here is strong."""

    def test_never_fails_even_far_above_the_threshold(self) -> None:
        c = check(ctx(acct_pd="12", federal_expenditures=50_000_000))
        assert c.status == "warn"
        assert c.status != "fail"

    def test_never_blocks(self) -> None:
        for expended in (None, 0, 10_000_000):
            c = check(ctx(acct_pd="12", federal_expenditures=expended))
            assert c.blocking is False

    def test_above_the_threshold_sends_them_to_the_sefa(self) -> None:
        c = check(ctx(acct_pd="12", federal_expenditures=2_140_338))
        assert c.status == "warn"
        assert "Schedule of Expenditures of Federal Awards" in c.detail

    def test_above_the_threshold_says_the_figure_is_not_the_right_one(self) -> None:
        c = check(ctx(acct_pd="12", federal_expenditures=2_140_338))
        assert "not the same as federal awards expended" in c.detail

    def test_below_the_threshold_still_warns_about_pass_through(self) -> None:
        # The most commonly omitted category, and the reason a "pass" here is a screen.
        c = check(ctx(acct_pd="12", federal_expenditures=100_000))
        assert c.status == "pass"
        assert "subawards" in c.detail

    def test_no_figure_is_unknown_not_pass(self) -> None:
        # Absence of a number must never read as "you are under the threshold".
        c = check(ctx(acct_pd="12"))
        assert c.status == "unknown"
        assert c.status != "pass"


class TestWhatItTellsYouWithoutTheFigure:
    def test_it_still_names_the_applicable_threshold(self) -> None:
        c = check(ctx(acct_pd="12"))
        assert "$1,000,000" in c.value
        assert "2026-01-01" in c.value

    def test_a_june_year_end_organization_gets_its_own_date(self) -> None:
        c = check(ctx(acct_pd="06"))
        assert "2026-07-01" in c.detail

    def test_it_explains_expended_not_received(self) -> None:
        c = check(ctx(acct_pd="12"))
        assert "spent rather than what was received" in c.detail

    def test_it_names_pass_through_subawards(self) -> None:
        c = check(ctx(acct_pd="12"))
        assert "passed through a state agency" in c.detail

    def test_without_an_accounting_period_it_gives_both_thresholds(self) -> None:
        c = check(ctx())
        assert c.status == "unknown"
        assert "$1,000,000" in c.detail
        assert "$750,000" in c.detail


class TestRegistryIntegration:
    def test_the_check_is_registered_and_in_the_audit_group(self) -> None:
        from grantcheck.checks import run_all

        checks = run_all(ctx(acct_pd="12"))
        audit = [c for c in checks if c.group == "audit_posture"]
        assert len(audit) == 1
        assert audit[0].id == "single_audit"

    def test_it_cannot_change_the_verdict_to_blocked(self) -> None:
        from grantcheck.checks import run_all
        from grantcheck.models import derive_readiness

        checks = run_all(
            ctx(
                acct_pd="12",
                federal_expenditures=99_000_000,
                subsection="03",
                exempt_status="01",
                foundation="15",
                filing_req_cd="06",
                in_pub78=1,
            )
        )
        assert derive_readiness(checks) != "blocked"
