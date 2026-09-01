"""TEOS parser tests, run against real committed slices of the real IRS files.

No mock-shaped fixtures anywhere in this module. The failure mode that matters is schema
drift, and a mock is blind to it by construction — it asserts that the parser agrees with
what we imagined, which is exactly the thing that goes stale.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from grantcheck.ingest.teos import (
    BMF_COLUMNS,
    ParseResult,
    is_group_subordinate,
    normalize_ein,
    parse_bmf,
    parse_epostcard,
    parse_irs_date,
    parse_mmddyyyy,
    parse_pub78,
    parse_revocation,
    parse_yyyymm,
)

FIXTURES = Path(__file__).parent / "fixtures" / "teos"


def load(name: str) -> str:
    """Read a fixture preserving its real line endings.

    ``read_text()`` without ``newline=""`` applies universal-newline translation, turning
    the file's real CRLF into LF. Every assertion about the actual bytes would then be
    testing a translated copy rather than what the IRS shipped.
    """
    return (FIXTURES / name).read_text(encoding="utf-8", newline="")


def sidecar(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.source.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bmf() -> ParseResult:
    return parse_bmf(load("bmf-sample.csv"))


@pytest.fixture(scope="module")
def pub78() -> ParseResult:
    return parse_pub78(load("pub78-sample.txt"))


@pytest.fixture(scope="module")
def revocation() -> ParseResult:
    return parse_revocation(load("revocation-sample.txt"))


@pytest.fixture(scope="module")
def epostcard() -> ParseResult:
    return parse_epostcard(load("epostcard-sample.txt"))


class TestFixtureProvenance:
    """Every fixture records where it came from. A fixture without provenance is a mock."""

    @pytest.mark.parametrize(
        "name",
        [
            "bmf-sample.csv",
            "pub78-sample.txt",
            "revocation-sample.txt",
            "epostcard-sample.txt",
            "epostcard-embedded-pipes.txt",
        ],
    )
    def test_sidecar_is_complete(self, name: str) -> None:
        meta = sidecar(name)
        assert meta["source_url"].startswith("https://")
        assert meta["upstream_sha256"]
        assert meta["retrieved_at"]
        assert meta["rows"] > 0
        assert meta["note"]


class TestLeadingBlankLines:
    """The three pipe files open with two blank lines. Real, and reproduced in fixtures."""

    @pytest.mark.parametrize(
        "name", ["pub78-sample.txt", "revocation-sample.txt", "epostcard-sample.txt"]
    )
    def test_fixture_starts_with_two_blank_lines(self, name: str) -> None:
        assert load(name).startswith("\r\n\r\n")

    def test_blank_lines_do_not_become_rows(self, pub78: ParseResult) -> None:
        assert pub78.rejected == 0
        assert all(r["ein"] for r in pub78.rows)


class TestPipeFilesHaveNoHeader:
    """Correction to the research notes, which said to read a header and map by name.

    There is no header in any of the three pipe-delimited files. The first non-blank line
    is data. A parser that skipped a "header" would silently drop a real organization.
    """

    def test_pub78_first_row_is_data(self, pub78: ParseResult) -> None:
        first = pub78.rows[0]
        assert first["ein"].isdigit()
        assert first["ein"] != "EIN".zfill(9)
        assert first["name"] and first["name"] != "NAME"

    def test_revocation_first_row_is_data(self, revocation: ParseResult) -> None:
        assert revocation.rows[0]["ein"].isdigit()

    def test_epostcard_first_row_is_data(self, epostcard: ParseResult) -> None:
        assert epostcard.rows[0]["ein"].isdigit()


class TestTrapEmbeddedPipes:
    """Trap: a literal pipe inside a field shifts the row and still parses.

    The pipe files carry no quoting convention. Five rows in the 2026-08-31 e-Postcard
    file contain a pipe inside the website or officer field. Split naively, the columns
    after the shift are still readable, so the result looks correct and is wrong. These
    must be quarantined and counted, never repaired by guessing.
    """

    def test_every_embedded_pipe_row_is_quarantined(self) -> None:
        result = parse_epostcard(load("epostcard-embedded-pipes.txt"))
        assert result.ok == 0, "no row with an embedded pipe may be accepted"
        assert result.rejected == 5
        assert result.quarantine_rate() == 1.0

    def test_quarantine_reports_line_number_and_reason(self) -> None:
        result = parse_epostcard(load("epostcard-embedded-pipes.txt"))
        for line_no, reason, raw in result.quarantined:
            assert line_no > 0
            assert "expected 26 fields" in reason
            assert raw

    def test_the_shifted_row_is_not_silently_accepted(self) -> None:
        # 232592298's website is "Home | Unity Foundation (...)". Split on the pipe, the
        # officer-name column would read "Unity Foundation (danealangston-bank...)" and
        # every field after it would be off by one — all still plausible strings.
        result = parse_epostcard(load("epostcard-embedded-pipes.txt"))
        assert "232592298" not in {r["ein"] for r in result.rows}
        raws = " ".join(raw for _, _, raw in result.quarantined)
        assert "232592298" in raws


class TestTrapBmfQuoting:
    """The inverse trap: the BMF *does* quote, so it must not be split naively.

    Twenty-nine rows in the 2026-08-10 vintage carry a comma inside a quoted field. The
    research notes describe the BMF only as "comma-delimited CSV" and do not mention
    quoting, which would lead straight to split(",").
    """

    def test_quoted_field_containing_a_comma_parses_as_one_field(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "030185556")
        assert row["name"] == "NORTH COUNTRY HOSPITAL & HEALTH CENTER,INC"
        # If the row had shifted, these would hold fragments of the address.
        assert row["state"] == "VT"
        assert row["subsection"] == "03"

    def test_naive_split_would_have_shifted_this_row(self) -> None:
        raw = next(
            line for line in load("bmf-sample.csv").split("\r\n") if line.startswith("030185556,")
        )
        assert len(raw.split(",")) != len(BMF_COLUMNS), "fixture no longer exercises the trap"

    def test_no_quoted_row_was_quarantined(self, bmf: ParseResult) -> None:
        assert bmf.rejected == 0


class TestTrapGroupSubordinates:
    """Trap: a group-exemption subordinate is legitimately absent from Publication 78.

    The central organization is listed and covers its subordinates. Reporting the absence
    as a deductibility problem tells a compliant organization it cannot receive
    tax-deductible contributions.
    """

    def test_subordinates_are_detected(self, bmf: ParseResult) -> None:
        subs = [r for r in bmf.rows if is_group_subordinate(r)]
        assert subs, "fixture must contain group subordinates"
        for r in subs:
            assert r["group_exemption"] not in ("", "0000")

    def test_zero_group_is_not_a_subordinate(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "271067272")
        assert row["group_exemption"] == "0000"
        assert is_group_subordinate(row) is False

    def test_subordinates_carry_affiliation_9(self, bmf: ParseResult) -> None:
        for r in bmf.rows:
            if is_group_subordinate(r):
                assert r["affiliation"] in ("7", "9")

    @pytest.mark.parametrize("group", ["0000", "", "   ", "00000"])
    def test_all_zero_forms_are_not_subordinates(self, group: str) -> None:
        assert is_group_subordinate({"group_exemption": group, "affiliation": "9"}) is False

    @pytest.mark.parametrize("group", ["3514", "3125", "0928"])
    def test_non_zero_group_with_subordinate_affiliation(self, group: str) -> None:
        assert is_group_subordinate({"group_exemption": group, "affiliation": "9"}) is True

    def test_central_organization_is_not_a_subordinate(self) -> None:
        # A central organization carries the group exemption number too, and IS listed in
        # Publication 78. Measured: affiliation 6 is 99.4% listed, affiliation 9 is 0.0%.
        assert is_group_subordinate({"group_exemption": "3514", "affiliation": "6"}) is False

    @pytest.mark.parametrize(
        ("affiliation", "expected"),
        [("9", True), ("7", True), ("6", False), ("8", False), ("3", False), ("", False)],
    )
    def test_affiliation_decides_not_group_alone(self, affiliation: str, expected: bool) -> None:
        row = {"group_exemption": "3514", "affiliation": affiliation}
        assert is_group_subordinate(row) is expected

    def test_boys_and_girls_clubs_central_is_listed_in_pub78(self, pub78) -> None:
        # The concrete case that proves group-alone is the wrong rule: BGCA carries
        # GROUP=3514 and is in Publication 78, because it is the central organization.
        assert "135562976" in {r["ein"] for r in pub78.rows}

    def test_subordinates_in_the_fixture_are_absent_from_pub78(
        self, bmf: ParseResult, pub78: ParseResult
    ) -> None:
        # The real relationship, demonstrated on real rows: this absence is normal and
        # must never be rendered as a failure.
        listed = {r["ein"] for r in pub78.rows}
        subs = [r["ein"] for r in bmf.rows if is_group_subordinate(r)]
        assert subs
        assert not (set(subs) & listed)


class TestTrapRevocationReinstatement:
    """Trap: presence on the revocation list does not mean currently revoked.

    Reinstated organizations remain on the list permanently with a reinstatement date.
    181,259 of 1,246,171 rows in the 2026-08-11 vintage are reinstated — roughly one in
    seven. Treating membership as revocation would wrongly block every one of them.
    """

    def test_fixture_has_both_kinds(self, revocation: ParseResult) -> None:
        reinstated = [r for r in revocation.rows if r["reinstatement_date"]]
        current = [r for r in revocation.rows if not r["reinstatement_date"]]
        assert reinstated, "fixture must contain reinstated organizations"
        assert current, "fixture must contain never-reinstated organizations"

    def test_reinstatement_date_is_parsed_not_dropped(self, revocation: ParseResult) -> None:
        row = next(r for r in revocation.rows if r["ein"] == "001037180")
        assert row["revocation_date"] == date(2013, 6, 15)
        assert row["reinstatement_date"] == date(2013, 6, 15)

    def test_absent_reinstatement_is_none_not_an_error(self, revocation: ParseResult) -> None:
        row = next(r for r in revocation.rows if r["ein"] == "000003154")
        assert row["revocation_date"] == date(2017, 11, 15)
        assert row["reinstatement_date"] is None
        assert revocation.rejected == 0

    def test_retroactive_reinstatement_is_representable(self, revocation: ParseResult) -> None:
        # Reinstatement is frequently retroactive to the revocation date itself, so the
        # rule must be "on or after", never "strictly after".
        same_day = [
            r
            for r in revocation.rows
            if r["reinstatement_date"] and r["reinstatement_date"] == r["revocation_date"]
        ]
        assert same_day, "fixture must exercise same-day retroactive reinstatement"


class TestTrapTaxPeriodIsNotAFilingDate:
    """Trap: BMF TAX_PERIOD is a month-precision period, not a filing date.

    Deriving "years since last filing" from it tells an organization that filed four
    months ago that it is delinquent. The parser keeps month precision so no caller can
    accidentally read a day out of it.
    """

    def test_tax_period_keeps_month_precision(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "271067272")
        assert row["tax_period"] == "2024-12"
        assert not isinstance(row["tax_period"], date)

    def test_ruling_keeps_month_precision(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "271067272")
        assert row["ruling"] == "2010-06"

    def test_blank_and_zero_tax_periods_are_none(self) -> None:
        assert parse_yyyymm("") is None
        assert parse_yyyymm("   ") is None
        assert parse_yyyymm("000000") is None

    @pytest.mark.parametrize("bad", ["2024", "20241", "2024123", "20241a", "202413", "202400"])
    def test_malformed_yyyymm_raises(self, bad: str) -> None:
        with pytest.raises(ValueError):
            parse_yyyymm(bad)


class TestDateParsing:
    def test_irs_dd_mon_yyyy(self) -> None:
        assert parse_irs_date("15-NOV-2017") == date(2017, 11, 15)
        assert parse_irs_date("01-JAN-2020") == date(2020, 1, 1)

    def test_case_insensitive_month(self) -> None:
        assert parse_irs_date("15-nov-2017") == date(2017, 11, 15)

    def test_empty_is_none(self) -> None:
        assert parse_irs_date("") is None
        assert parse_irs_date("   ") is None

    @pytest.mark.parametrize("bad", ["2017-11-15", "15-XXX-2017", "15/NOV/2017", "NOV-2017"])
    def test_malformed_raises(self, bad: str) -> None:
        with pytest.raises(ValueError):
            parse_irs_date(bad)

    def test_epostcard_mm_dd_yyyy(self) -> None:
        assert parse_mmddyyyy("04-01-2009") == date(2009, 4, 1)
        assert parse_mmddyyyy("12-31-2025") == date(2025, 12, 31)

    def test_the_two_date_formats_are_not_interchangeable(self) -> None:
        # 04-01-2009 is 1 April in the e-Postcard file. Read with the revocation parser it
        # would raise rather than silently become 4 January.
        with pytest.raises(ValueError):
            parse_irs_date("04-01-2009")


class TestEinNormalization:
    def test_zero_pads_to_nine(self) -> None:
        assert normalize_ein("19818") == "000019818"
        assert normalize_ein("000019818") == "000019818"

    def test_strips_whitespace_and_hyphens(self) -> None:
        assert normalize_ein(" 27-1067272 ") == "271067272"

    def test_files_agree_after_normalization(self, bmf: ParseResult, pub78: ParseResult) -> None:
        assert all(len(r["ein"]) == 9 for r in bmf.rows)
        assert all(len(r["ein"]) == 9 for r in pub78.rows)


class TestBmfHeaderContract:
    def test_expected_columns(self, bmf: ParseResult) -> None:
        assert len(BMF_COLUMNS) == 28
        assert BMF_COLUMNS[0] == "EIN"
        assert "ACTIVITY" in BMF_COLUMNS  # present in the real file, absent from the notes
        assert bmf.ok > 0

    def test_a_changed_header_fails_loudly(self) -> None:
        # Silently parsing positionally against an unknown layout would shift every field.
        text = "EIN,NAME,SOMETHING_NEW\r\n271067272,X,Y\r\n"
        with pytest.raises(ValueError, match="header changed"):
            parse_bmf(text)

    def test_empty_input_is_empty_not_an_error(self) -> None:
        assert parse_bmf("").ok == 0


class TestParseResultAccounting:
    def test_counts_add_up(self) -> None:
        result = parse_epostcard(load("epostcard-embedded-pipes.txt"))
        assert result.ok + result.rejected == 5

    def test_clean_fixtures_have_a_zero_quarantine_rate(
        self, bmf: ParseResult, pub78: ParseResult, revocation: ParseResult
    ) -> None:
        for result in (bmf, pub78, revocation):
            assert result.quarantine_rate() == 0.0


class TestNamedVerificationOrganizations:
    """The roster from the build prompt, checked against real BMF rows.

    These assertions are what will catch an upstream change in a specific organization's
    record — a re-classification, a move, a group ruling — which is the kind of drift that
    quietly changes what the tool reports.
    """

    def test_packard_is_a_private_foundation(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "942278431")
        assert row["name"] == "DAVID AND LUCILE PACKARD FOUNDATION"
        assert row["foundation"] == "04"  # drives the organization_type warning
        assert row["subsection"] == "03"

    def test_boys_and_girls_clubs_is_a_central_organization(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "135562976")
        assert row["group_exemption"] == "3514"

    def test_code_for_america(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "271067272")
        assert row["name"] == "CODE FOR AMERICA LABS"
        assert row["state"] == "CA"
        assert row["ntee_cd"] == "W20"
        assert row["subsection"] == "03"

    def test_second_harvest(self, bmf: ParseResult) -> None:
        row = next(r for r in bmf.rows if r["ein"] == "942614101")
        assert row["name"] == "SECOND HARVEST OF SILICON VALLEY"
        assert row["state"] == "CA"
