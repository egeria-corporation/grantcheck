"""SAM.gov matching and the three federal-registration checks.

The name-matching tests use real IRS legal names taken from the committed Business Master
File fixture, paired with the more verbose form a SAM.gov registration typically carries.
The SAM side is constructed rather than real: the Entity Extracts API needs a key that this
build does not have yet, so the *parser* for that extract is not written and is not being
tested here. What is tested is the matching, the confidence, and the check semantics, all of
which are ours rather than upstream's.
"""

from __future__ import annotations

from datetime import date

import pytest

from grantcheck.checks import CheckContext
from grantcheck.checks import sam_expiration as expiration_check
from grantcheck.checks import sam_registration as registration_check
from grantcheck.checks import uei as uei_check
from grantcheck.ingest.matching import (
    CONFIDENCE_FLOOR,
    Candidate,
    match,
    name_similarity,
    normalize_name,
    pin,
)
from grantcheck.models import Vintage

TODAY = date(2026, 9, 1)
SAM_VINTAGE = Vintage("sam", date(2026, 8, 29), "https://open.gsa.gov/api/entity-api/")


def ctx(**row: object) -> CheckContext:
    base: dict[str, object] = {
        "in_bmf": 1,
        "in_pub78": 0,
        "in_revocation": 0,
        "in_epostcard": 0,
    }
    base.update(row)
    return CheckContext(ein="271067272", row=base, vintages={"sam": SAM_VINTAGE}, today=TODAY)


class TestNameNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("CODE FOR AMERICA LABS", "CODE FOR AMERICA LABS"),
            ("Code for America Labs, Inc.", "CODE FOR AMERICA LABS"),
            ("THE NATURE CONSERVANCY", "NATURE CONSERVANCY"),
            ("Boys & Girls Clubs of America", "BOYS AND GIRLS CLUBS OF AMERICA"),
            ("SECOND HARVEST FOOD BANK, INC", "SECOND HARVEST FOOD BANK"),
            ("Some Org LLC", "SOME ORG"),
            ("WIKIMEDIA FOUNDATION ORG", "WIKIMEDIA FOUNDATION ORG"),
            ("Riverkeeper Assn", "RIVERKEEPER ASSOCIATION"),
            ("Natl Council Intl Affairs", "NATIONAL COUNCIL INTERNATIONAL AFFAIRS"),
        ],
    )
    def test_normalizes(self, raw: str, expected: str) -> None:
        assert normalize_name(raw) == expected

    def test_medial_the_is_kept(self) -> None:
        # "FRIENDS OF THE LIBRARY" is not the same phrase without it.
        assert normalize_name("Friends of the Library") == "FRIENDS OF THE LIBRARY"

    def test_foundation_is_not_stripped(self) -> None:
        # Deliberate deviation from the build prompt, which lists FOUNDATION alongside the
        # legal-form suffixes. FOUNDATION is part of an organization's identity rather than
        # its legal form, and dropping it collapses distinct names together for no gain.
        assert normalize_name("Packard Foundation") == "PACKARD FOUNDATION"

    @pytest.mark.parametrize("token", ["ORG", "COMM", "SOC"])
    def test_ambiguous_abbreviations_are_left_alone(self, token: str) -> None:
        """Real counterexample: the IRS legal name for Wikimedia is
        "WIKIMEDIA FOUNDATION ORG", where ORG is the .org domain rather than an
        abbreviation of "organization". COMM is Community, Commission, or Committee; SOC is
        Society or Social. Expanding any of them invents a token one side does not have.
        """
        assert token in normalize_name(f"Example {token} Group")

    def test_wikimedias_real_name_survives(self) -> None:
        # The real BMF row is "WIKIMEDIA FOUNDATION ORG".
        score = name_similarity("WIKIMEDIA FOUNDATION ORG", "Wikimedia Foundation, Inc.")
        assert score >= CONFIDENCE_FLOOR

    def test_empty_input(self) -> None:
        assert normalize_name("") == ""


class TestNameSimilarity:
    def test_identical_after_normalization_is_one(self) -> None:
        assert name_similarity("CODE FOR AMERICA LABS", "Code for America Labs, Inc.") == 1.0

    def test_inserted_words_still_match_strongly(self) -> None:
        # The real shape of the problem: the IRS legal name is terse, the SAM registration
        # is verbose. This pair is the same organization.
        score = name_similarity(
            "SECOND HARVEST OF SILICON VALLEY",
            "Second Harvest Food Bank of Silicon Valley, Inc.",
        )
        assert score >= CONFIDENCE_FLOOR

    def test_different_organizations_score_low(self) -> None:
        assert name_similarity("FEEDING AMERICA", "AMERICAN NATIONAL RED CROSS") < 0.6

    def test_generic_names_are_not_over_rewarded(self) -> None:
        # Two genuinely different community health centres must not look like one another
        # just because they share three common words.
        score = name_similarity(
            "RIVERSIDE COMMUNITY HEALTH CENTER", "OAKLAND COMMUNITY HEALTH CENTER"
        )
        assert score < 0.95

    def test_empty_scores_zero(self) -> None:
        assert name_similarity("", "ANYTHING") == 0.0


class TestMatching:
    def test_exact_match_in_the_same_state(self) -> None:
        result = match(
            irs_name="CODE FOR AMERICA LABS",
            irs_sort_name=None,
            state="CA",
            city="SAN FRANCISCO",
            candidates=[
                Candidate("KX7TLM4NBQF3", "Code for America Labs, Inc.", "CA", "SAN FRANCISCO")
            ],
        )
        assert result.confident
        assert result.tier == "exact"
        assert result.candidate.uei == "KX7TLM4NBQF3"

    def test_state_is_a_hard_filter(self) -> None:
        # An identically named entity in another state is not this organization. Letting a
        # perfect name score override the state is how a tool matches the wrong one of forty
        # similarly named community organizations.
        result = match(
            irs_name="CODE FOR AMERICA LABS",
            irs_sort_name=None,
            state="CA",
            city=None,
            candidates=[Candidate("XXXXXXXXXXXX", "Code for America Labs, Inc.", "NY")],
        )
        assert not result.confident
        assert result.candidate is None

    def test_ambiguity_between_two_close_candidates_is_not_a_match(self) -> None:
        # Chapters of a national organization in one state look exactly like this. Picking
        # the higher score would be a coin flip presented as a fact.
        result = match(
            irs_name="BOYS AND GIRLS CLUBS OF AMERICA",
            irs_sort_name=None,
            state="GA",
            city=None,
            candidates=[
                Candidate("AAAAAAAAAAAA", "Boys and Girls Clubs of America", "GA"),
                Candidate("BBBBBBBBBBBB", "Boys & Girls Clubs of America Inc", "GA"),
            ],
        )
        assert not result.confident
        assert "ambiguous" in result.note

    def test_below_the_floor_says_what_to_do(self) -> None:
        result = match(
            irs_name="FEEDING AMERICA",
            irs_sort_name=None,
            state="IL",
            city=None,
            candidates=[Candidate("ZZZZZZZZZZZZ", "Chicago Symphony Orchestra", "IL")],
        )
        assert not result.confident
        assert "--uei" in result.note

    def test_the_sort_name_is_tried_as_well(self) -> None:
        # The BMF sort name is often the name the public knows, and is sometimes what the
        # organization used when registering with SAM.
        result = match(
            irs_name="LELAND STANFORD JUNIOR UNIVERSITY BOARD OF TRUSTEES",
            irs_sort_name="STANFORD UNIVERSITY",
            state="CA",
            city=None,
            candidates=[Candidate("SU0000000001", "Stanford University", "CA")],
        )
        assert result.confident

    def test_city_agreement_cannot_lift_junk_over_the_floor(self) -> None:
        result = match(
            irs_name="FEEDING AMERICA",
            irs_sort_name=None,
            state="IL",
            city="CHICAGO",
            candidates=[Candidate("ZZZZZZZZZZZZ", "Chicago Symphony Orchestra", "IL", "CHICAGO")],
        )
        assert not result.confident

    def test_no_candidates(self) -> None:
        result = match(irs_name="X", irs_sort_name=None, state="CA", city=None, candidates=[])
        assert not result.confident
        assert result.score == 0.0

    def test_a_match_is_never_presented_as_a_lookup(self) -> None:
        result = match(
            irs_name="CODE FOR AMERICA LABS",
            irs_sort_name=None,
            state="CA",
            city=None,
            candidates=[Candidate("KX7TLM4NBQF3", "Code for America Labs, Inc.", "CA")],
        )
        assert "inference, not a lookup" in result.note
        assert "--uei" in result.note

    def test_pinning_skips_inference(self) -> None:
        result = pin(Candidate("KX7TLM4NBQF3", "Whatever The Registration Says", "CA"))
        assert result.confident
        assert result.method == "pinned"
        assert result.score == 1.0


class TestLowConfidenceReportsUnknownNotFailure:
    """ "We could not identify you" must never read as "your registration is missing".

    They are different claims with different consequences, and only one of them is about
    the organization.
    """

    @pytest.mark.parametrize(
        ("check_fn", "check_id"),
        [
            (registration_check.check, "sam_registration"),
            (expiration_check.check, "sam_expiration"),
            (uei_check.check, "uei"),
        ],
    )
    def test_unmatched_is_unknown(self, check_fn, check_id: str) -> None:
        c = check_fn(ctx())
        assert c.status == "unknown"
        assert c.status != "fail"
        assert c.id == check_id

    def test_unmatched_tells_the_reader_to_pin_it(self) -> None:
        c = registration_check.check(ctx())
        assert "--uei" in c.detail

    def test_unmatched_says_it_is_a_join_limitation(self) -> None:
        c = registration_check.check(ctx())
        assert "not a finding about the" in c.detail

    def test_all_three_say_the_same_thing(self) -> None:
        # A reader must not see one problem reported as three separate failures.
        details = {
            registration_check.check(ctx()).detail,
            expiration_check.check(ctx()).detail,
            uei_check.check(ctx()).detail,
        }
        assert len(details) == 1

    def test_unknown_does_not_block(self) -> None:
        from grantcheck.models import derive_readiness

        checks = [registration_check.check(ctx()), uei_check.check(ctx())]
        assert derive_readiness(checks) != "blocked"


class TestRegistrationStatus:
    def test_active_passes(self) -> None:
        c = registration_check.check(ctx(sam_status="Active", sam_match_confidence=0.95))
        assert c.status == "pass"

    def test_not_found_is_distinct_from_expired(self) -> None:
        # Different failures with different remedies: registering takes weeks, renewing
        # takes ten to fifteen business days. Collapsing them misleads about the timeline.
        c = registration_check.check(ctx(sam_match_confidence=0.95, sam_status=""))
        assert c.status == "fail"
        assert "different problem from an expired" in c.detail

    def test_inactive_is_a_blocking_failure(self) -> None:
        c = registration_check.check(ctx(sam_status="Inactive", sam_match_confidence=0.95))
        assert c.status == "fail"
        assert c.blocking is True

    def test_contracts_only_purpose_is_flagged(self) -> None:
        # An entity registered for contracts only is active and still cannot take a grant.
        c = registration_check.check(
            ctx(
                sam_status="Active",
                sam_purpose="FEDERAL_CONTRACTS_ONLY",
                sam_match_confidence=0.95,
            )
        )
        assert c.status == "warn"
        assert "cannot receive a grant" in c.detail

    def test_assistance_purpose_passes(self) -> None:
        c = registration_check.check(
            ctx(sam_status="Active", sam_purpose="ALL_AWARDS", sam_match_confidence=0.95)
        )
        assert c.status == "pass"


class TestExpiration:
    def test_comfortably_current_passes(self) -> None:
        c = expiration_check.check(
            ctx(sam_status="Active", sam_expiration="2027-03-14", sam_match_confidence=0.95)
        )
        assert c.status == "pass"
        assert "194 days out" in c.value

    def test_expired_is_a_blocking_failure(self) -> None:
        c = expiration_check.check(
            ctx(sam_status="Active", sam_expiration="2026-05-02", sam_match_confidence=0.95)
        )
        assert c.status == "fail"
        assert c.blocking is True
        assert "122 days ago" in c.detail

    @pytest.mark.parametrize("expires", ["2026-09-15", "2026-10-15", "2026-10-31"])
    def test_active_but_expiring_soon_is_a_warning_not_a_pass(self, expires: str) -> None:
        # The quiet disqualification: status says Active, and it lapses before the award.
        c = expiration_check.check(
            ctx(sam_status="Active", sam_expiration=expires, sam_match_confidence=0.95)
        )
        assert c.status == "warn"
        assert "not automatic" in c.detail

    def test_the_threshold_is_sixty_days(self) -> None:
        just_inside = expiration_check.check(
            ctx(sam_status="Active", sam_expiration="2026-10-31", sam_match_confidence=0.95)
        )
        just_outside = expiration_check.check(
            ctx(sam_status="Active", sam_expiration="2026-11-01", sam_match_confidence=0.95)
        )
        assert just_inside.status == "warn"
        assert just_outside.status == "pass"

    def test_missing_expiration_is_unknown_not_a_failure(self) -> None:
        c = expiration_check.check(ctx(sam_status="Active", sam_match_confidence=0.95))
        assert c.status == "unknown"


class TestUei:
    def test_present_passes(self) -> None:
        c = uei_check.check(ctx(uei="KX7TLM4NBQF3", sam_match_confidence=0.95))
        assert c.status == "pass"
        assert c.value == "KX7TLM4NBQF3"

    def test_absent_with_a_confident_match_is_a_failure(self) -> None:
        c = uei_check.check(ctx(sam_match_confidence=0.95, sam_status="Active"))
        assert c.status == "fail"
        assert "sam.gov" in c.detail.lower()


class TestPinnedUei:
    def test_pinning_produces_a_definite_answer(self) -> None:
        c = uei_check.check(
            ctx(uei="KX7TLM4NBQF3", sam_match_confidence=1.0, sam_match_method="pinned")
        )
        assert c.status == "pass"
        assert c.value == "KX7TLM4NBQF3"


class TestNoSamDataAtAll:
    """An index build without SAM.gov data must not produce findings about registrations.

    This is a different situation from a low-confidence match, and different again from a
    confident match that found no registration. Reporting "no registration found" from our
    own missing data would be a finding about the organization drawn from nothing.
    """

    def no_sam_ctx(self, **row: object) -> CheckContext:
        base: dict[str, object] = {"in_bmf": 1}
        base.update(row)
        return CheckContext(ein="271067272", row=base, vintages={}, today=TODAY)

    @pytest.mark.parametrize(
        ("check_fn", "check_id"),
        [
            (registration_check.check, "sam_registration"),
            (expiration_check.check, "sam_expiration"),
            (uei_check.check, "uei"),
        ],
    )
    def test_reports_not_checked(self, check_fn, check_id: str) -> None:
        c = check_fn(self.no_sam_ctx())
        assert c.status == "unknown"
        assert c.value == "Not checked"
        assert c.id == check_id

    def test_says_nothing_about_the_organization(self) -> None:
        c = registration_check.check(self.no_sam_ctx())
        assert "Nothing here says anything about" in c.detail

    def test_a_pinned_uei_does_not_manufacture_a_finding(self) -> None:
        # Knowing which registration to look at does not help when there is nothing to look
        # at. Before this guard, pinning produced a hard "No registration found" failure.
        c = registration_check.check(
            self.no_sam_ctx(uei="KX7TLM4NBQF3", sam_match_confidence=1.0, sam_match_method="pinned")
        )
        assert c.status == "unknown"
        assert c.status != "fail"

    def test_a_pinned_uei_is_still_reported(self) -> None:
        # The UEI the user supplied is a fact we do have, so it is reported as one.
        c = uei_check.check(
            self.no_sam_ctx(uei="KX7TLM4NBQF3", sam_match_confidence=1.0, sam_match_method="pinned")
        )
        assert c.status == "pass"
        assert c.value == "KX7TLM4NBQF3"


class TestVerdictDoesNotOverclaim:
    """READY TO APPLY printed over three unknowns is its own kind of dishonest."""

    def test_summary_names_the_unchecked_items(self) -> None:
        from datetime import UTC, datetime

        from grantcheck.models import Report
        from grantcheck.render.table import _verdict_summary

        checks = [
            registration_check.check(
                CheckContext(ein="271067272", row={"in_bmf": 1}, vintages={}, today=TODAY)
            )
        ]
        report = Report(
            ein="27-1067272",
            queried_at=datetime(2026, 9, 1, tzinfo=UTC),
            readiness="ready",
            checks=checks,
        )
        assert _verdict_summary(report) == "1 item could not be checked"

    def test_readiness_itself_is_unchanged(self) -> None:
        # The rule stays as specified: an unchecked thing is not a failed thing.
        from grantcheck.models import derive_readiness

        checks = [
            registration_check.check(
                CheckContext(ein="271067272", row={"in_bmf": 1}, vintages={}, today=TODAY)
            )
        ]
        assert derive_readiness(checks) == "ready"
