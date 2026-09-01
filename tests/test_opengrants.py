"""Optional enrichment, and the guarantee that it stays optional.

The rule: grantcheck is complete without an OpenGrants account. These tests assert that as
a property of the output rather than trusting it — with no key, a bad key, a rate-limited
key, a timeout, or the network down, the report must be **byte-identical** to the one built
with no key at all, and the exit code must not move.

An enrichment layer that can break the core command is not optional, whatever a README
says. That is what would make this "open source but you need an account".
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from grantcheck.ingest.build import DatasetVintage, build_index, merge_datasets, write_manifest
from grantcheck.ingest.teos import parse_bmf, parse_epostcard, parse_pub78, parse_revocation
from grantcheck.models import Opportunity
from grantcheck.render import json as json_render
from grantcheck.render import markdown, table
from grantcheck.report import build_report
from grantcheck.sources import opengrants
from grantcheck.sources.index import IndexClient

FIXTURES = Path(__file__).parent / "fixtures" / "teos"
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
TODAY = date(2026, 9, 1)


def load(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8")


VINTAGES = [
    DatasetVintage("bmf", date(2026, 8, 10), "https://www.irs.gov/pub/irs-soi/eo1.csv", 49),
    DatasetVintage("pub78", date(2026, 8, 11), "https://apps.irs.gov/x/pub78.zip", 23),
    DatasetVintage("revocation", date(2026, 8, 11), "https://apps.irs.gov/x/rev.zip", 29),
    DatasetVintage("epostcard", date(2026, 8, 31), "https://apps.irs.gov/x/ep.zip", 11),
]

GOOD_RESPONSE = {
    "data": [
        {
            "id": "og-1",
            "title": "Community Development Block Grant",
            "funder": "HUD",
            "deadline": "2026-11-30",
            "url": "https://example.gov/cdbg",
        }
    ]
}


@pytest.fixture(scope="module")
def published(tmp_path_factory: pytest.TempPathFactory) -> Path:
    merged = merge_datasets(
        bmf=parse_bmf(load("bmf-sample.csv")),
        pub78=parse_pub78(load("pub78-sample.txt")),
        revocation=parse_revocation(load("revocation-sample.txt")),
        epostcard=parse_epostcard(load("epostcard-sample.txt")),
    )
    out = tmp_path_factory.mktemp("published")
    manifest = build_index(
        merged=merged, vintages=VINTAGES, out_dir=out, vintage="2026-08", built_at=NOW
    )
    write_manifest(manifest, out)
    return out / "2026-08"


class Serving(httpx.BaseTransport):
    def __init__(self, root: Path) -> None:
        self.root = root

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = self.root / request.url.path.rsplit("/", 1)[-1]
        if not path.exists():
            return httpx.Response(404, content=b"missing")
        return httpx.Response(200, content=path.read_bytes())


@pytest.fixture
def client(published: Path, tmp_path: Path) -> IndexClient:
    return IndexClient(
        base="https://index.test",
        cache=tmp_path / "cache",
        client=httpx.Client(transport=Serving(published), base_url="https://index.test"),
    )


def report_without_key(client: IndexClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENGRANTS_API_KEY", raising=False)
    return build_report("27-1067272", client=client, today=TODAY, now=NOW)


class TestWithoutAKey:
    def test_the_report_is_complete(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = report_without_key(client, monkeypatch)
        assert report.readiness == "ready"
        assert len(report.checks) == 11
        assert report.opportunities is None

    def test_output_never_mentions_the_key(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No nag. Tools that beg for signups do not get adopted, and the README mentions
        # the key exactly once.
        report = report_without_key(client, monkeypatch)
        for rendered in (
            table.render(report, color=False, unicode_glyphs=False),
            markdown.render(report),
            json_render.render(report),
        ):
            lowered = rendered.lower()
            assert "opengrants_api_key" not in lowered
            assert "api key" not in lowered
            assert "sign up" not in lowered

    def test_no_enrichment_section_appears(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Not an empty heading, not a hint the section could exist.
        report = report_without_key(client, monkeypatch)
        rendered = table.render(report, color=False, unicode_glyphs=False)
        assert "OPPORTUNITIES" not in rendered
        assert "OpenGrants" not in rendered

    def test_exit_code_is_unaffected(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert report_without_key(client, monkeypatch).exit_code == 0


class TestEveryFailurePathIsByteIdentical:
    """The acceptance criterion, asserted on bytes rather than on intent."""

    @pytest.fixture
    def baseline(self, client: IndexClient, monkeypatch: pytest.MonkeyPatch) -> str:
        return json_render.render(report_without_key(client, monkeypatch))

    def _with_transport(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch, transport
    ) -> str:
        """Run the real client against a failing transport, through the real report path."""
        monkeypatch.setenv("OPENGRANTS_API_KEY", "a-key-that-will-not-work")

        # Capture the real function before patching: referencing it by name inside the
        # replacement would call the replacement.
        real = opengrants.match_opportunities

        def routed(**kwargs):
            return real(
                **kwargs,
                client=httpx.Client(transport=transport),
                base_url="https://og.test",
            )

        monkeypatch.setattr(opengrants, "match_opportunities", routed)
        report = build_report("27-1067272", client=client, today=TODAY, now=NOW)
        return json_render.render(report)

    @pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503])
    def test_error_statuses(
        self,
        client: IndexClient,
        monkeypatch: pytest.MonkeyPatch,
        baseline: str,
        status: int,
    ) -> None:
        class Failing(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(status, json={"error": "nope"})

        assert self._with_transport(client, monkeypatch, Failing()) == baseline

    def test_network_down(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch, baseline: str
    ) -> None:
        class Dead(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("no route to host")

        assert self._with_transport(client, monkeypatch, Dead()) == baseline

    def test_timeout(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch, baseline: str
    ) -> None:
        class Slow(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                raise httpx.ReadTimeout("too slow")

        assert self._with_transport(client, monkeypatch, Slow()) == baseline

    def test_malformed_json(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch, baseline: str
    ) -> None:
        class Garbage(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, content=b"<html>not json</html>")

        assert self._with_transport(client, monkeypatch, Garbage()) == baseline

    def test_unexpected_shape(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch, baseline: str
    ) -> None:
        # A response that changed shape must produce no enrichment rather than a
        # half-populated row presented as a live result.
        class Reshaped(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={"data": [{"unexpected": "shape"}]})

        assert self._with_transport(client, monkeypatch, Reshaped()) == baseline

    def test_empty_result_set(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch, baseline: str
    ) -> None:
        class Empty(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={"data": []})

        assert self._with_transport(client, monkeypatch, Empty()) == baseline


class TestTheClientItself:
    def test_no_key_means_no_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENGRANTS_API_KEY", raising=False)

        class Exploding(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                raise AssertionError("no request may be made without a key")

        assert (
            opengrants.match_opportunities(
                ein="271067272", client=httpx.Client(transport=Exploding())
            )
            is None
        )

    def test_blank_key_is_treated_as_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENGRANTS_API_KEY", "   ")
        assert opengrants.api_key() is None

    def test_a_successful_call_returns_opportunities(self) -> None:
        class Ok(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                assert request.headers["Authorization"] == "Bearer test-key"
                return httpx.Response(
                    200, json=GOOD_RESPONSE, headers={"X-RateLimit-Remaining": "97"}
                )

        result = opengrants.match_opportunities(
            ein="271067272",
            key="test-key",
            client=httpx.Client(transport=Ok()),
            base_url="https://og.test",
        )
        assert result is not None
        assert result.opportunities[0].title == "Community Development Block Grant"
        assert result.opportunities[0].deadline == date(2026, 11, 30)
        assert result.rate_limit_remaining == "97"

    def test_the_key_never_appears_in_the_returned_object(self) -> None:
        class Ok(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json=GOOD_RESPONSE)

        result = opengrants.match_opportunities(
            ein="271067272",
            key="super-secret",
            client=httpx.Client(transport=Ok()),
            base_url="https://og.test",
        )
        assert "super-secret" not in repr(result)


class TestEnrichmentOnlyOnACleanReport:
    def test_not_attempted_when_the_report_is_not_ready(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Enrichment is for the moment the tool has just said nothing is stopping you.
        # Offering opportunities to a blocked organization would be tone-deaf and wasteful.
        monkeypatch.setenv("OPENGRANTS_API_KEY", "k")
        called: list[str] = []
        monkeypatch.setattr(
            opengrants, "match_opportunities", lambda **kw: called.append("x") or None
        )
        report = build_report("99-9999999", client=client, today=TODAY, now=NOW)
        assert report.readiness != "ready"
        assert called == []

    def test_enrich_false_skips_it_entirely(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENGRANTS_API_KEY", "k")
        called: list[str] = []
        monkeypatch.setattr(
            opengrants, "match_opportunities", lambda **kw: called.append("x") or None
        )
        build_report("27-1067272", client=client, today=TODAY, now=NOW, enrich=False)
        assert called == []


class TestEnrichedOutputIsMarked:
    """Users must always know which facts are public-source and which are live."""

    def a_report_with_opportunities(self, client: IndexClient, monkeypatch):
        monkeypatch.setenv("OPENGRANTS_API_KEY", "k")
        monkeypatch.setattr(
            opengrants,
            "match_opportunities",
            lambda **kw: opengrants.Enrichment(
                opportunities=[
                    Opportunity(
                        id="og-1",
                        title="Community Development Block Grant",
                        funder="HUD",
                        deadline=date(2026, 11, 30),
                        url="https://example.gov/cdbg",
                    )
                ]
            ),
        )
        return build_report("27-1067272", client=client, today=TODAY, now=NOW)

    def test_terminal_carries_the_marker(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = self.a_report_with_opportunities(client, monkeypatch)
        rendered = table.render(report, color=False, unicode_glyphs=True)
        assert opengrants.MARKER in rendered
        assert "Community Development Block Grant" in rendered

    def test_markdown_carries_the_marker(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = self.a_report_with_opportunities(client, monkeypatch)
        assert opengrants.MARKER in markdown.render(report)

    def test_json_carries_the_opportunities(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json as jsonlib

        report = self.a_report_with_opportunities(client, monkeypatch)
        parsed = jsonlib.loads(json_render.render(report))
        assert parsed["opportunities"][0]["id"] == "og-1"

    def test_the_enriched_report_still_validates(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from jsonschema import Draft202012Validator

        report = self.a_report_with_opportunities(client, monkeypatch)
        Draft202012Validator(json_render.schema()).validate(report.to_dict())

    def test_the_exit_code_is_unchanged_by_enrichment(
        self, client: IndexClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert self.a_report_with_opportunities(client, monkeypatch).exit_code == 0
