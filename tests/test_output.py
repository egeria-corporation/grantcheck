"""Output formats, the JSON contract, and exit codes.

The JSON is a public contract that the hosted site must match byte for byte, so it is
validated against the committed schema rather than eyeballed.
"""

from __future__ import annotations

import json as jsonlib
import os
import sys
from datetime import UTC, date, datetime

import pytest
from click.testing import CliRunner
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from grantcheck.cli import main
from grantcheck.models import (
    EXIT_ATTENTION,
    EXIT_BLOCKED,
    EXIT_ERROR,
    EXIT_NOT_FOUND,
    EXIT_OK,
    Check,
    Opportunity,
    Organization,
    Report,
    Vintage,
)
from grantcheck.render import json as json_render
from grantcheck.render import markdown, table

BMF = Vintage("bmf", date(2026, 8, 10), "https://www.irs.gov/pub/irs-soi/eo1.csv")
SAM = Vintage("sam", date(2026, 8, 29), "https://open.gsa.gov/api/entity-api/")


def a_report(**overrides: object) -> Report:
    base: dict[str, object] = {
        "ein": "27-1067272",
        "queried_at": datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
        "readiness": "attention",
        "organization": Organization(
            ein="27-1067272",
            name="CODE FOR AMERICA LABS",
            city="SAN FRANCISCO",
            state="CA",
            ntee_code="W20",
            subsection="03",
            ruling_date="2010-06",
        ),
        "checks": [
            Check(
                id="exempt_status",
                label="Exempt status",
                group="tax_exemption",
                status="pass",
                blocking=True,
                value="501(c)(3), unconditional exemption",
                detail="Recognized under section 501(c)(3).",
                vintage=BMF,
            ),
            Check(
                id="organization_type",
                label="Organization type",
                group="tax_exemption",
                status="warn",
                blocking=False,
                value="Private foundation",
                detail="Most federal programs exclude private foundations.",
                vintage=BMF,
            ),
            Check(
                id="sam_registration",
                label="SAM.gov registration",
                group="federal_registration",
                status="unknown",
                blocking=True,
                value="Not checked",
                detail="No SAM.gov data in this index build.",
                vintage=None,
                confidence=None,
            ),
        ],
        "blocking_check_ids": [],
        "vintages": [BMF, SAM],
        "notes": ["Matched to SAM.gov by legal name and state, confidence 0.91"],
    }
    base.update(overrides)
    return Report(**base)  # type: ignore[arg-type]


class TestJsonSchema:
    """The schema itself is committed and tested, not just asserted to exist."""

    def test_the_schema_is_valid(self) -> None:
        Draft202012Validator.check_schema(json_render.schema())

    def test_a_full_report_validates(self) -> None:
        Draft202012Validator(json_render.schema()).validate(a_report().to_dict())

    def test_a_not_found_report_validates(self) -> None:
        report = a_report(
            readiness="not_found", organization=None, checks=[], blocking_check_ids=[]
        )
        Draft202012Validator(json_render.schema()).validate(report.to_dict())

    def test_an_enriched_report_validates(self) -> None:
        report = a_report(
            opportunities=[
                Opportunity(
                    id="og-1",
                    title="Community Development Block Grant",
                    funder="HUD",
                    deadline=date(2026, 11, 30),
                )
            ]
        )
        Draft202012Validator(json_render.schema()).validate(report.to_dict())

    def test_the_schema_rejects_an_unknown_status(self) -> None:
        # Proves the schema constrains rather than rubber-stamps.
        payload = a_report().to_dict()
        payload["checks"][0]["status"] = "probably_fine"
        with pytest.raises(ValidationError):
            Draft202012Validator(json_render.schema()).validate(payload)

    def test_the_schema_rejects_a_bad_ein_format(self) -> None:
        payload = a_report().to_dict()
        payload["ein"] = "271067272"
        with pytest.raises(ValidationError):
            Draft202012Validator(json_render.schema()).validate(payload)

    def test_the_schema_requires_the_disclosure(self) -> None:
        payload = a_report().to_dict()
        del payload["disclosure"]
        with pytest.raises(ValidationError):
            Draft202012Validator(json_render.schema()).validate(payload)


class TestJsonOutput:
    def test_is_parseable(self) -> None:
        parsed = jsonlib.loads(json_render.render(a_report()))
        assert parsed["ein"] == "27-1067272"

    def test_carries_schema_version(self) -> None:
        assert jsonlib.loads(json_render.render(a_report()))["schema_version"] == "1.0"

    def test_unknown_is_null_never_empty_string(self) -> None:
        parsed = jsonlib.loads(json_render.render(a_report()))
        sam = next(c for c in parsed["checks"] if c["id"] == "sam_registration")
        assert sam["vintage"] is None
        assert sam["confidence"] is None

    def test_ends_with_a_newline(self) -> None:
        assert json_render.render(a_report()).endswith("\n")

    def test_round_trips_back_into_a_report(self) -> None:
        original = a_report()
        restored = Report.from_dict(jsonlib.loads(json_render.render(original)))
        assert restored == original


class TestMarkdownOutput:
    def test_has_the_organization_and_ein(self) -> None:
        out = markdown.render(a_report())
        assert "Code For America Labs" in out
        assert "27-1067272" in out

    def test_uses_tables_not_glyphs(self) -> None:
        out = markdown.render(a_report())
        assert "| | Check | Finding | As of |" in out
        for glyph in ("✔", "⚠", "✘"):
            assert glyph not in out

    def test_spells_out_the_status(self) -> None:
        out = markdown.render(a_report())
        assert "| OK |" in out
        assert "| Attention |" in out

    def test_carries_the_disclosure(self) -> None:
        assert a_report().disclosure in markdown.render(a_report())

    def test_names_sources_with_their_vintages(self) -> None:
        out = markdown.render(a_report())
        assert "IRS EO Business Master File, published 2026-08-10" in out

    def test_a_pipe_in_a_value_does_not_break_the_table(self) -> None:
        report = a_report(
            checks=[
                Check(
                    id="x",
                    label="Odd | label",
                    group="tax_exemption",
                    status="pass",
                    blocking=False,
                    value="a | b",
                    vintage=BMF,
                )
            ]
        )
        row = next(line for line in markdown.render(report).splitlines() if "Odd" in line)
        # Escaped pipes are still pipe characters, so count only the unescaped delimiters.
        assert row.replace("\\|", "").count("|") == 5  # four cells, five delimiters
        assert "\\|" in row

    def test_explains_warnings_below_the_table(self) -> None:
        out = markdown.render(a_report())
        assert "**Organization type.**" in out


def _collapse(text: str) -> str:
    """Whitespace-normalize, so a line-wrapped disclosure still compares as verbatim."""
    return " ".join(text.split())


RENDERERS = [
    ("table", lambda r: table.render(r, color=False, unicode_glyphs=True)),
    ("table-ascii", lambda r: table.render(r, color=False, unicode_glyphs=False)),
    ("markdown", markdown.render),
    ("json", json_render.render),
]


class TestDisclosureInEveryFormat:
    """Program conventions: verbatim, in every format, every time.

    The terminal wraps at 80 columns, so the text is present unaltered but line-broken.
    Comparing on collapsed whitespace tests the requirement rather than where the breaks
    happen to fall.
    """

    @pytest.mark.parametrize(("name", "render_fn"), RENDERERS)
    def test_present(self, name: str, render_fn) -> None:
        report = a_report()
        assert _collapse(report.disclosure) in _collapse(render_fn(report))

    @pytest.mark.parametrize("readiness", ["ready", "attention", "blocked", "not_found"])
    @pytest.mark.parametrize(("name", "render_fn"), RENDERERS)
    def test_present_at_every_readiness(self, name: str, render_fn, readiness: str) -> None:
        report = a_report(readiness=readiness)
        assert _collapse(report.disclosure) in _collapse(render_fn(report))

    def test_the_ascii_form_is_still_the_same_sentence(self) -> None:
        # Transliteration must not touch the disclosure: it is plain ASCII already.
        out = table.render(a_report(), color=False, unicode_glyphs=False)
        assert _collapse(a_report().disclosure) in _collapse(out)


class TestTerminalPresentation:
    def test_wraps_at_eighty_columns(self) -> None:
        out = table.render(a_report(), color=False, unicode_glyphs=False)
        for line in out.splitlines():
            assert len(line) <= 80, f"{len(line)} columns: {line!r}"

    def test_no_color_env_suppresses_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        assert table.supports_color() is False

    def test_color_can_be_forced_off(self) -> None:
        out = table.render(a_report(), color=False, unicode_glyphs=False)
        assert "\033[" not in out

    def test_color_appears_when_enabled(self) -> None:
        out = table.render(a_report(), color=True, unicode_glyphs=False)
        assert "\033[" in out

    def test_ascii_mode_emits_no_non_ascii(self) -> None:
        # A default Windows console is cp1252 and cannot encode the glyphs or the rule.
        out = table.render(a_report(), color=False, unicode_glyphs=False)
        out.encode("ascii")


class TestExitCodes:
    @pytest.mark.parametrize(
        ("readiness", "expected"),
        [
            ("ready", EXIT_OK),
            ("blocked", EXIT_BLOCKED),
            ("attention", EXIT_ATTENTION),
            ("not_found", EXIT_NOT_FOUND),
        ],
    )
    def test_report_exposes_the_documented_code(self, readiness: str, expected: int) -> None:
        assert a_report(readiness=readiness).exit_code == expected

    def test_invalid_ein_exits_one_without_touching_the_network(self) -> None:
        # 00-0000000 must fail on format. A network call here would be a bug.
        result = CliRunner().invoke(main, ["--ein", "00-0000000"])
        assert result.exit_code == EXIT_ERROR
        assert "all zeros" in result.output + str(result.stderr_bytes or b"")

    def test_malformed_ein_exits_one(self) -> None:
        result = CliRunner().invoke(main, ["--ein", "not-an-ein"])
        assert result.exit_code == EXIT_ERROR

    def test_help_documents_every_exit_code(self) -> None:
        result = CliRunner().invoke(main, ["--help"])
        assert result.exit_code == 0
        for code in ("0", "1", "2", "3", "4"):
            assert code in result.output
        assert "not found" in result.output
        assert "blocked" in result.output

    def test_format_choices_are_offered(self) -> None:
        result = CliRunner().invoke(main, ["--help"])
        for fmt in ("table", "markdown", "json"):
            assert fmt in result.output


class TestNoColorIsHonouredEndToEnd:
    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "")
        # Present but empty still means "no colour" per the NO_COLOR convention.
        assert os.environ.get("NO_COLOR") is not None
        assert table.supports_color() is False


class TestFileFormatsAreUtf8:
    """Markdown and JSON are file formats and must be UTF-8 on every platform.

    On Windows a redirected stdout defaults to the ANSI code page, so
    `grantcheck --format markdown > report.md` wrote cp1252 — a file that is not valid
    UTF-8 anywhere else. Reconfiguring sys.stdout was not enough either: click caches its
    own text wrapper around the original stream, so characters were already replaced by the
    time the encoding changed. The fix writes encoded bytes to the underlying buffer.
    """

    def test_write_utf8_emits_utf8_bytes(self) -> None:
        import io

        from grantcheck.cli import _write_utf8

        class FakeStdout:
            def __init__(self) -> None:
                self.buffer = io.BytesIO()

        fake = FakeStdout()
        original = sys.stdout
        sys.stdout = fake  # type: ignore[assignment]
        try:
            _write_utf8("middle dot \u00b7 em dash \u2014 done")
        finally:
            sys.stdout = original

        written = fake.buffer.getvalue()
        assert written.decode("utf-8") == "middle dot \u00b7 em dash \u2014 done"
        assert b"\xc2\xb7" in written  # UTF-8 for U+00B7, not the cp1252 single byte 0xb7
        assert b"\xe2\x80\x94" in written  # UTF-8 for U+2014

    def test_write_utf8_falls_back_on_a_captured_stream(self) -> None:
        # CliRunner and similar harnesses hand over a text stream with no .buffer.
        import io

        from grantcheck.cli import _write_utf8

        captured = io.StringIO()  # a text stream, and StringIO has no .buffer
        assert not hasattr(captured, "buffer")

        original = sys.stdout
        sys.stdout = captured
        try:
            _write_utf8("middle dot · done")
        finally:
            sys.stdout = original

        assert "·" in captured.getvalue()

    def test_markdown_and_json_are_the_designated_file_formats(self) -> None:
        from grantcheck.cli import FILE_FORMATS

        assert sorted(FILE_FORMATS) == ["json", "markdown"]
        # The table format is terminal output and adapts to the terminal instead.
        assert "table" not in FILE_FORMATS

    def test_rendered_markdown_keeps_real_typography(self) -> None:
        out = markdown.render(a_report())
        assert "\u00b7" in out  # the identity separator survives as a real character
        out.encode("utf-8")
