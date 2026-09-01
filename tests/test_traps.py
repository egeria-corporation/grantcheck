"""The four correctness traps, each named after the wrong answer it prevents.

These are not edge cases. Each affects hundreds of thousands of organizations, and each
produces output that looks right and is badly wrong. They are tested against real rows from
the real IRS files wherever a real row exists.

The wrong answers, stated plainly:

1. Telling ~238,000 group-exemption subordinates they cannot receive deductible
   contributions, because the central organization is the one listed in Publication 78.
2. Telling ~181,000 reinstated organizations they are revoked, because reinstated
   organizations stay on the revocation list forever.
3. Telling ~1.5 million small filers they have never filed, because the Form 990-N
   e-Postcard is not in the Form 990 e-file index.
4. Telling an organization that filed on time it is years delinquent, because BMF
   ``TAX_PERIOD`` is a processing period rather than a filing date.
"""

from __future__ import annotations

from datetime import date

import pytest

from grantcheck.checks import CheckContext, run_all
from grantcheck.checks import filing_recency as recency_check
from grantcheck.checks import most_recent_filing as filing_check
from grantcheck.checks import pub78 as pub78_check
from grantcheck.models import Vintage, derive_readiness

TODAY = date(2026, 9, 1)

VINTAGES = {
    "bmf": Vintage("bmf", date(2026, 8, 10), "https://www.irs.gov/pub/irs-soi/eo1.csv"),
    "pub78": Vintage("pub78", date(2026, 8, 11), "https://apps.irs.gov/x/pub78.zip"),
    "revocation": Vintage("revocation", date(2026, 8, 11), "https://apps.irs.gov/x/rev.zip"),
    "epostcard": Vintage("epostcard", date(2026, 8, 31), "https://apps.irs.gov/x/ep.zip"),
}


def ctx(**row: object) -> CheckContext:
    """Build a context from an index row, defaulting every presence flag to absent."""
    base: dict[str, object] = {
        "in_bmf": 0,
        "in_pub78": 0,
        "in_revocation": 0,
        "in_epostcard": 0,
    }
    base.update(row)
    return CheckContext(
        ein=str(base.get("ein", "271067272")),
        row=base,
        vintages=VINTAGES,
        today=TODAY,
    )


def find(checks: list, check_id: str):
    return next(c for c in checks if c.id == check_id)


# ---------------------------------------------------------------------------------------
# Trap 1
# ---------------------------------------------------------------------------------------


class TestTrap1GroupSubordinateAbsentFromPub78:
    """A subordinate under a group ruling is absent from Publication 78 by design.

    The central organization is listed and the ruling covers its subordinates. Measured on
    the real files: AFFILIATION 9 is 0.0% listed across 237,871 organizations, while
    AFFILIATION 6 (central) is 99.4% listed. Reporting the absence as a deductibility
    problem is a false accusation.
    """

    def test_subordinate_absent_from_pub78_is_not_applicable(self) -> None:
        c = pub78_check.check(ctx(in_bmf=1, in_pub78=0, group_exemption="3514", affiliation="9"))
        assert c.status == "not_applicable"
        assert c.status != "fail"
        assert "3514" in c.detail
        assert "not a problem" in c.detail.lower()

    def test_the_group_number_is_named_so_the_reader_can_act(self) -> None:
        c = pub78_check.check(ctx(in_bmf=1, in_pub78=0, group_exemption="0928", affiliation="9"))
        assert "0928" in c.detail
        assert "central organization" in c.detail

    def test_central_organization_is_not_excused(self) -> None:
        # Boys & Girls Clubs of America carries GROUP=3514 and AFFILIATION=6, and IS listed
        # in Publication 78. Keying on GROUP alone would wrongly suppress the check for
        # ~2,560 central organizations that should be listed.
        c = pub78_check.check(ctx(in_bmf=1, in_pub78=0, group_exemption="3514", affiliation="6"))
        assert c.status == "warn"
        assert c.status != "not_applicable"

    def test_a_subordinate_is_not_flagged_delinquent_for_filing(self) -> None:
        # The second half of the same trap: subordinates are covered by the central
        # organization's group return and frequently have no filings of their own.
        c = recency_check.check(
            ctx(in_bmf=1, group_exemption="3514", affiliation="9", filing_req_cd="01")
        )
        assert c.status == "not_applicable"
        assert c.status not in ("fail", "warn")

    def test_a_subordinate_never_produces_blocked(self) -> None:
        checks = run_all(
            ctx(
                in_bmf=1,
                in_pub78=0,
                group_exemption="3514",
                affiliation="9",
                subsection="03",
                exempt_status="01",
                foundation="15",
                filing_req_cd="01",
            )
        )
        assert derive_readiness(checks) != "blocked"


# ---------------------------------------------------------------------------------------
# Trap 2
# ---------------------------------------------------------------------------------------


class TestTrap2RevokedThenReinstated:
    """Presence on the revocation list does not mean currently revoked.

    181,259 of 1,246,171 rows in the 2026-08-11 vintage carry a reinstatement date. Reading
    membership alone as revoked would tell roughly one listed organization in seven that it
    cannot receive federal money.
    """

    def test_reinstated_organization_passes(self) -> None:
        from grantcheck.checks import auto_revocation

        c = auto_revocation.check(
            ctx(
                in_revocation=1,
                revocation_date="2013-06-15",
                revocation_posting_date="2013-10-21",
                reinstatement_date="2013-06-15",
            )
        )
        assert c.status == "pass"

    def test_the_full_history_is_reported_not_hidden(self) -> None:
        from grantcheck.checks import auto_revocation

        c = auto_revocation.check(
            ctx(
                in_revocation=1,
                revocation_date="2019-05-15",
                reinstatement_date="2020-11-15",
            )
        )
        assert "2019-05-15" in c.value
        assert "2020-11-15" in c.value
        assert "good standing" in c.detail

    def test_retroactive_reinstatement_on_the_same_day_passes(self) -> None:
        # Reinstatement is frequently retroactive to the revocation date itself. A strict
        # "after" comparison would report thousands of reinstated organizations as revoked.
        from grantcheck.checks import auto_revocation

        c = auto_revocation.check(
            ctx(
                in_revocation=1,
                revocation_date="2013-06-15",
                reinstatement_date="2013-06-15",
            )
        )
        assert c.status == "pass"

    def test_never_reinstated_is_blocked(self) -> None:
        from grantcheck.checks import auto_revocation

        c = auto_revocation.check(
            ctx(
                in_revocation=1,
                revocation_date="2023-05-15",
                revocation_posting_date="2023-08-14",
                reinstatement_date=None,
            )
        )
        assert c.status == "fail"
        assert c.blocking is True
        assert "Rev" in c.detail and "2014-11" in c.detail  # points at the cure

    def test_reinstatement_predating_a_later_revocation_does_not_cure_it(self) -> None:
        # The repeat-revocation case: revoked 2013, reinstated 2013, revoked again 2017.
        # Carrying the old reinstatement forward would report a revoked organization as
        # being in good standing.
        from grantcheck.checks import auto_revocation

        c = auto_revocation.check(
            ctx(
                in_revocation=1,
                revocation_date="2017-06-15",
                reinstatement_date="2013-06-15",
            )
        )
        assert c.status == "fail"
        assert "previous revocation cycle" in c.detail

    def test_absent_from_the_list_passes(self) -> None:
        from grantcheck.checks import auto_revocation

        c = auto_revocation.check(ctx(in_bmf=1, in_revocation=0))
        assert c.status == "pass"


# ---------------------------------------------------------------------------------------
# Trap 3
# ---------------------------------------------------------------------------------------


class TestTrap3NinetyNineNOnlyFiler:
    """Filing recency must union the 990-N e-Postcard file with the e-file index.

    Most exempt organizations file the 990-N, which is not in the Form 990 e-file XML index
    at all. Building recency from the index alone reports 1.5 million small nonprofits as
    having never filed and three years delinquent.
    """

    def test_epostcard_filing_is_found(self) -> None:
        c = filing_check.check(
            ctx(
                in_bmf=1,
                in_epostcard=1,
                epostcard_period_end="2025-12-31",
                epostcard_tax_year="2025",
            )
        )
        assert c.status == "pass"
        assert "2025-12-31" in c.value

    def test_recency_is_computed_from_the_epostcard_period(self) -> None:
        c = recency_check.check(
            ctx(
                in_bmf=1,
                in_epostcard=1,
                epostcard_period_end="2025-12-31",
                epostcard_tax_year="2025",
                filing_req_cd="02",
            )
        )
        assert c.status == "pass"
        assert c.value == "0"

    def test_a_990n_filer_is_not_reported_delinquent(self) -> None:
        # The exact failure: present in the e-Postcard file, absent from the e-file index.
        checks = run_all(
            ctx(
                in_bmf=1,
                in_pub78=1,
                in_epostcard=1,
                epostcard_period_end="2025-06-30",
                epostcard_tax_year="2024",
                subsection="03",
                exempt_status="01",
                foundation="15",
                filing_req_cd="02",
            )
        )
        assert find(checks, "filing_recency").status == "pass"
        assert find(checks, "most_recent_filing").status == "pass"
        assert derive_readiness(checks) == "ready"

    def test_the_source_is_named_in_the_detail(self) -> None:
        c = filing_check.check(
            ctx(
                in_bmf=1,
                in_epostcard=1,
                epostcard_period_end="2025-12-31",
                epostcard_tax_year="2025",
            )
        )
        assert "990-N" in c.detail


# ---------------------------------------------------------------------------------------
# Trap 4
# ---------------------------------------------------------------------------------------


class TestTrap4TaxPeriodIsNotAFilingDate:
    """BMF ``TAX_PERIOD`` is a processed-return period, not a filing date.

    It lags actual filing by weeks to more than a year. Treating it as a filing date and
    counting years from it tells an organization that filed four months ago that it is
    delinquent.
    """

    def test_the_fallback_can_never_produce_a_failure(self) -> None:
        # Even at eight years, the BMF fallback caps at a warning, because the number
        # itself is not trustworthy enough to accuse anyone with.
        c = recency_check.check(ctx(in_bmf=1, tax_period="2018-12", filing_req_cd="01"))
        assert c.status == "warn"
        assert c.status != "fail"

    @pytest.mark.parametrize("tax_period", ["2018-12", "2015-06", "2010-01"])
    def test_no_fallback_value_produces_a_failure(self, tax_period: str) -> None:
        c = recency_check.check(ctx(in_bmf=1, tax_period=tax_period, filing_req_cd="01"))
        assert c.status != "fail"

    def test_the_fallback_says_it_is_a_processing_period(self) -> None:
        c = recency_check.check(ctx(in_bmf=1, tax_period="2024-12", filing_req_cd="01"))
        assert "processed" in c.detail
        assert "not a filing date" in c.detail or "rather than a filing date" in c.detail

    def test_most_recent_filing_labels_the_fallback(self) -> None:
        c = filing_check.check(ctx(in_bmf=1, tax_period="2024-12"))
        assert "not a filing date" in c.detail
        assert "lags filing" in c.detail or "lag" in c.detail

    def test_an_authoritative_source_outranks_the_fallback(self) -> None:
        # Where both exist, the real filing record wins and full severity is available.
        evidence = filing_check.resolve_evidence(
            ctx(in_bmf=1, in_epostcard=1, epostcard_period_end="2025-12-31", tax_period="2019-12")
        )
        assert evidence.source == "epostcard"
        assert evidence.authoritative is True

    def test_month_precision_is_read_as_the_month_end(self) -> None:
        # The conservative direction: month end makes the organization look more recently
        # filed, so the fallback can never manufacture a delinquency.
        assert filing_check._month_end("2024-02") == date(2024, 2, 29)
        assert filing_check._month_end("2024-12") == date(2024, 12, 31)
        assert filing_check._month_end("2023-02") == date(2023, 2, 28)


# ---------------------------------------------------------------------------------------
# The fifth population, discovered in the real data
# ---------------------------------------------------------------------------------------


class TestOrganizationsWithNoFilingRequirement:
    """433,337 subsection-03 organizations are not required to file at all.

    Churches (287,356), religious organizations, state instrumentalities, and code-00
    organizations. They cannot be delinquent because nothing was ever due, and 22% of the
    501(c)(3) universe is far too large a population to get wrong.
    """

    @pytest.mark.parametrize("code", ["00", "06", "07", "13", "14"])
    def test_never_flagged_delinquent(self, code: str) -> None:
        c = recency_check.check(ctx(in_bmf=1, filing_req_cd=code))
        assert c.status == "not_applicable"

    @pytest.mark.parametrize("code", ["00", "06", "07", "13", "14"])
    def test_absent_filing_history_is_expected_not_a_gap(self, code: str) -> None:
        c = filing_check.check(ctx(in_bmf=1, filing_req_cd=code))
        assert c.status == "not_applicable"
        assert "not a problem" in c.detail

    def test_a_church_with_no_filings_is_ready(self) -> None:
        checks = run_all(
            ctx(
                in_bmf=1,
                in_pub78=1,
                subsection="03",
                exempt_status="01",
                foundation="10",
                filing_req_cd="06",
            )
        )
        assert derive_readiness(checks) == "ready"

    def test_a_group_return_filer_is_not_delinquent(self) -> None:
        c = recency_check.check(ctx(in_bmf=1, filing_req_cd="03"))
        assert c.status == "not_applicable"
        assert "group return" in c.detail


class TestUnknownNeverBlocksAcrossTheRegistry:
    """Asserted over the whole registry, not per check.

    An unchecked thing is not a failed thing. This is the assertion that has to survive
    every future check being added.
    """

    def test_an_empty_row_produces_no_blocking_failure(self) -> None:
        checks = run_all(ctx())
        assert derive_readiness(checks) != "blocked"
        assert all(not (c.status == "fail" and c.blocking) for c in checks)

    def test_every_check_returns_a_known_status(self) -> None:
        from grantcheck.models import GROUPS, STATUSES

        for row in ({}, {"in_bmf": 1}, {"in_bmf": 1, "subsection": "03", "exempt_status": "01"}):
            for c in run_all(ctx(**row)):
                assert c.status in STATUSES
                assert c.group in GROUPS

    def test_every_non_unknown_check_carries_a_vintage(self) -> None:
        checks = run_all(
            ctx(in_bmf=1, in_pub78=1, subsection="03", exempt_status="01", foundation="15")
        )
        for c in checks:
            if c.status != "unknown":
                assert c.vintage is not None, f"{c.id} has no vintage"


class TestPrivateFoundationsStillFile:
    """Private foundations file a Form 990-PF and are subject to revocation like anyone else.

    They carry ``FILING_REQ_CD = 00``, which alone reads as "no annual return required".
    129,561 of them in the 2026-08-10 vintage also carry ``PF_FILING_REQ_CD = 1``. Reading
    only the first code would tell every one of them it has no filing obligation — wrong in
    the direction that lets a real delinquency go unnoticed.

    Only 4,507 organizations have both codes clear and genuinely owe nothing.
    """

    def test_a_private_foundation_is_not_exempt_from_filing(self) -> None:
        assert (
            filing_check.exempt_from_filing(ctx(in_bmf=1, filing_req_cd="00", pf_filing_req_cd="1"))
            is None
        )

    def test_recency_still_applies_to_a_private_foundation(self) -> None:
        c = recency_check.check(
            ctx(in_bmf=1, filing_req_cd="00", pf_filing_req_cd="1", tax_period="2024-12")
        )
        assert c.status != "not_applicable"

    def test_both_codes_clear_is_genuinely_exempt(self) -> None:
        reason = filing_check.exempt_from_filing(
            ctx(in_bmf=1, filing_req_cd="00", pf_filing_req_cd="0")
        )
        assert reason == "not required to file"

    def test_the_real_packard_row_is_not_reported_as_exempt(self) -> None:
        # FILING_REQ_CD=00, PF_FILING_REQ_CD=1, FOUNDATION=04 — the real values.
        c = recency_check.check(
            ctx(
                in_bmf=1,
                filing_req_cd="00",
                pf_filing_req_cd="1",
                foundation="04",
                tax_period="2024-12",
            )
        )
        assert c.value != "No annual return required"

    def test_a_church_is_still_exempt(self) -> None:
        # The guard must not swallow the genuine no-filing populations.
        assert filing_check.exempt_from_filing(
            ctx(in_bmf=1, filing_req_cd="06", pf_filing_req_cd="0")
        )
