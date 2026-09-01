"""EIN normalization, validation, formatting, and shard-prefix extraction."""

import pytest

from grantcheck.ein import InvalidEIN, format_ein, is_valid, normalize, prefix

CANONICAL = "270125367"


class TestAcceptedForms:
    @pytest.mark.parametrize(
        "raw",
        [
            "27-0125367",  # the form a human writes
            "270125367",  # the form the IRS bulk files carry
            "27 0125367",  # the form that survives a copy out of a PDF
            "  27-0125367  ",  # surrounding whitespace
            "27–0125367",  # en dash, substituted by word processors
            "27—0125367",  # em dash, same
            "\t27-0125367\n",  # tabs and newlines
            "27 0125367",  # non-breaking space, from a web page
        ],
    )
    def test_normalizes_to_nine_digits(self, raw: str) -> None:
        assert normalize(raw) == CANONICAL

    def test_leading_zero_is_preserved(self) -> None:
        # Some IRS files drop a leading zero; some do not. Both must key the same, and
        # the zero must survive normalization rather than being eaten by an int cast.
        assert normalize("01-2345678") == "012345678"
        assert format_ein("012345678") == "01-2345678"


class TestRejectedInput:
    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "\n", "\t\t"],
    )
    def test_empty_and_whitespace_only(self, raw: str) -> None:
        with pytest.raises(InvalidEIN, match="No EIN given"):
            normalize(raw)

    def test_none(self) -> None:
        with pytest.raises(InvalidEIN, match="No EIN given"):
            normalize(None)  # type: ignore[arg-type]

    @pytest.mark.parametrize("raw", [270125367, 27.0, [], {}])
    def test_non_string(self, raw: object) -> None:
        with pytest.raises(InvalidEIN, match="must be text"):
            normalize(raw)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("raw", "digits"),
        [("2701253", 7), ("2701253678", 10), ("1", 1)],
    )
    def test_wrong_length_says_how_many_it_found(self, raw: str, digits: int) -> None:
        with pytest.raises(InvalidEIN, match=f"has {digits} digits"):
            normalize(raw)

    @pytest.mark.parametrize("raw", ["27-012536X", "abcdefghi", "27/0125367", "27.0125367"])
    def test_non_digit_characters(self, raw: str) -> None:
        with pytest.raises(InvalidEIN, match="not digits"):
            normalize(raw)

    def test_only_separators(self) -> None:
        with pytest.raises(InvalidEIN, match="no digits"):
            normalize("---")

    def test_prefix_00_is_not_issued(self) -> None:
        # Section 10 of the build prompt requires 00-0000000 to fail on format and never
        # reach the network.
        with pytest.raises(InvalidEIN, match="starts with 00"):
            normalize("00-0000000")

    def test_well_formed_but_absent_ein_passes_format_validation(self) -> None:
        # 99-9999999 is well-formed. It must reach the index and come back not_found,
        # which is a different outcome from a format error.
        assert normalize("99-9999999") == "999999999"


class TestUnicodeDigits:
    """Unicode decimal digits must be rejected, not silently accepted.

    ``str.isdigit()`` and ``int()`` both accept these. If normalization used either, an
    EIN pasted from a document using non-ASCII numerals would validate and then miss every
    lookup in the index — a wrong answer rather than an error message.
    """

    @pytest.mark.parametrize(
        ("raw", "description"),
        [
            ("٢٧٠١٢٥٣٦٧", "Arabic-Indic"),
            ("２７０１２５３６７", "full-width"),
            ("۲۷۰۱۲۵۳۶۷", "Extended Arabic-Indic"),
            ("၂၇၀၁၂၅၃၆၇", "Myanmar"),
        ],
    )
    def test_rejected(self, raw: str, description: str) -> None:
        assert raw.isdigit(), f"{description} sample should be str.isdigit()-true to be a real test"
        with pytest.raises(InvalidEIN, match="not digits"):
            normalize(raw)

    def test_superscript_digits_rejected(self) -> None:
        with pytest.raises(InvalidEIN, match="not digits"):
            normalize("²⁷⁰¹²⁵³⁶⁷")


class TestFormatting:
    def test_format_from_any_accepted_form(self) -> None:
        for raw in ("270125367", "27-0125367", "27 0125367"):
            assert format_ein(raw) == "27-0125367"

    def test_format_rejects_invalid(self) -> None:
        with pytest.raises(InvalidEIN):
            format_ein("nope")


class TestPrefix:
    def test_prefix_is_the_first_two_digits(self) -> None:
        assert prefix("27-0125367") == "27"
        assert prefix("012345678") == "01"

    def test_prefix_accepts_any_form(self) -> None:
        assert prefix("27 0125367") == prefix("270125367") == "27"


class TestIsValid:
    @pytest.mark.parametrize("raw", ["27-0125367", "270125367", "99-9999999"])
    def test_true_for_valid(self, raw: str) -> None:
        assert is_valid(raw)

    @pytest.mark.parametrize("raw", ["", "abc", "00-0000000", "1234", "٢٧٠١٢٥٣٦٧"])
    def test_false_for_invalid(self, raw: str) -> None:
        assert is_valid(raw) is False

    def test_never_raises(self) -> None:
        for raw in ("", None, 5, "---", "x" * 200):
            assert is_valid(raw) in (True, False)  # type: ignore[arg-type]


class TestErrorMessagesAreActionable:
    """Every rejection tells the reader what the expected form is.

    These messages are read by grant consultants, not developers.
    """

    @pytest.mark.parametrize("raw", ["", "abc", "1234", "00-0000000", "27/0125367"])
    def test_message_shows_an_example(self, raw: str) -> None:
        with pytest.raises(InvalidEIN) as excinfo:
            normalize(raw)
        assert "27-0125367" in str(excinfo.value)
        assert "nine digits" in str(excinfo.value)
