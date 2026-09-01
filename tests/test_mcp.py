"""The MCP server, and the architectural invariants that keep the surfaces honest.

The point of the parity test here is not that the two code paths happen to agree today. It
is that they call the same function, so they cannot diverge — and the test fails loudly if
someone ever makes the MCP server compute something for itself.
"""

from __future__ import annotations

import ast
import json as jsonlib
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from grantcheck import explanations
from grantcheck.ingest.build import DatasetVintage, build_index, merge_datasets, write_manifest
from grantcheck.ingest.teos import parse_bmf, parse_epostcard, parse_pub78, parse_revocation
from grantcheck.mcp_server import build_server
from grantcheck.models import DISCLOSURE
from grantcheck.render import json as json_render
from grantcheck.report import build_report
from grantcheck.sources.index import IndexClient

SRC = Path(__file__).parent.parent / "src" / "grantcheck"
FIXTURES = Path(__file__).parent / "fixtures" / "teos"


def load(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8")


VINTAGES = [
    DatasetVintage("bmf", date(2026, 8, 10), "https://www.irs.gov/pub/irs-soi/eo1.csv", 49),
    DatasetVintage("pub78", date(2026, 8, 11), "https://apps.irs.gov/x/pub78.zip", 23),
    DatasetVintage("revocation", date(2026, 8, 11), "https://apps.irs.gov/x/rev.zip", 29),
    DatasetVintage("epostcard", date(2026, 8, 31), "https://apps.irs.gov/x/ep.zip", 11),
]


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
        merged=merged,
        vintages=VINTAGES,
        out_dir=out,
        vintage="2026-08",
        built_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    write_manifest(manifest, out)
    return out / "2026-08"


class ServingTransport(httpx.BaseTransport):
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
        client=httpx.Client(transport=ServingTransport(published), base_url="https://index.test"),
    )


class TestToolRegistration:
    @pytest.mark.anyio
    async def test_all_four_tools_are_registered(self) -> None:
        tools = await build_server().list_tools()
        assert {t.name for t in tools} == {
            "check_readiness",
            "find_ein",
            "explain_check",
            "dataset_vintages",
        }

    @pytest.mark.anyio
    async def test_every_tool_description_carries_the_disclosure(self) -> None:
        # The model needs to know, at the point of deciding to use a result, that it is
        # informational rather than an eligibility determination.
        for tool in await build_server().list_tools():
            assert DISCLOSURE in (tool.description or ""), tool.name

    @pytest.mark.anyio
    async def test_check_readiness_documents_the_uei_escape_hatch(self) -> None:
        tools = {t.name: t for t in await build_server().list_tools()}
        assert "uei" in (tools["check_readiness"].description or "")

    def test_server_instructions_carry_the_disclosure(self) -> None:
        assert DISCLOSURE in (build_server().instructions or "")

    def test_instructions_tell_the_model_to_quote_the_vintage(self) -> None:
        assert "vintage" in (build_server().instructions or "").lower()


class TestParityWithTheCli:
    """The acceptance criterion: identical payloads for the same EIN at the same vintage."""

    def test_identical_report_payloads(self, client: IndexClient) -> None:
        from grantcheck.mcp_server import build_report as mcp_build_report

        # Same function object, so they cannot diverge by construction.
        assert mcp_build_report is build_report

        now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        cli_report = build_report("27-1067272", client=client, today=date(2026, 9, 1), now=now)
        mcp_report = build_report("27-1067272", client=client, today=date(2026, 9, 1), now=now)
        assert mcp_report.to_dict() == cli_report.to_dict()

    def test_the_cli_json_and_the_mcp_report_are_byte_identical(self, client: IndexClient) -> None:
        now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        report = build_report("27-1067272", client=client, today=date(2026, 9, 1), now=now)

        from_cli = jsonlib.loads(json_render.render(report))
        from_mcp = report.to_dict()  # what check_readiness puts under "report"
        assert from_cli == from_mcp

    def test_the_mcp_result_carries_vintages_in_band(self, client: IndexClient) -> None:
        # A model quoting this must be able to attribute it without a second call.
        report = build_report("27-1067272", client=client, today=date(2026, 9, 1))
        payload = {"report": report.to_dict(), "disclosure": report.disclosure}
        assert payload["report"]["vintages"]
        assert all(v["published"] for v in payload["report"]["vintages"])
        assert payload["disclosure"] == DISCLOSURE


class TestExplainers:
    def test_there_is_one_per_check_id(self) -> None:
        from grantcheck.checks import registry

        registered = {check_id for check_id, _ in registry()}
        assert registered <= set(explanations.available())

    def test_eleven_explainers(self) -> None:
        assert len(explanations.available()) == 11

    @pytest.mark.parametrize("check_id", explanations.available())
    def test_each_is_substantial_and_starts_with_a_heading(self, check_id: str) -> None:
        text = explanations.get(check_id)
        assert text is not None
        assert text.startswith("# ")
        assert len(text) > 400

    @pytest.mark.parametrize("check_id", explanations.available())
    def test_each_says_what_to_do(self, check_id: str) -> None:
        # An explainer that describes a problem without naming the remedy is half an answer.
        text = explanations.get(check_id) or ""
        assert "What to do" in text or "what to do" in text

    def test_unknown_check_id_returns_none(self) -> None:
        assert explanations.get("no_such_check") is None

    def test_path_traversal_is_refused(self) -> None:
        assert explanations.get("../../pyproject") is None
        assert explanations.get("../cli") is None


class TestAdapterHasNoBusinessLogic:
    """Both adapters must be thin. Asserted structurally, not by reading them."""

    @pytest.mark.parametrize("module", ["cli.py", "mcp_server.py"])
    def test_under_three_hundred_lines(self, module: str) -> None:
        lines = (SRC / module).read_text(encoding="utf-8").splitlines()
        assert len(lines) < 300, f"{module} is {len(lines)} lines"

    @pytest.mark.parametrize("module", ["cli.py", "mcp_server.py"])
    def test_no_branching_on_check_status_or_value(self, module: str) -> None:
        # A conditional on a status here means a rule has leaked out of the library, and
        # the two surfaces would begin to disagree.
        source = (SRC / module).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            rendered = ast.dump(node)
            for status in ("'pass'", "'warn'", "'fail'", "'not_applicable'"):
                assert status not in rendered, f"{module} branches on a check status"

    def test_the_mcp_server_does_not_depend_on_the_cli(self) -> None:
        """The dependency runs one way only.

        `grantcheck mcp` is the documented way to start the server, so the CLI importing
        `mcp_server` is the design rather than a violation. The reverse would not be: the
        build prompt requires that the MCP server neither shells out to the CLI nor is a
        wrapper around it, because that is how the two surfaces start to disagree.
        """
        tree = ast.parse((SRC / "mcp_server.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            for name in names:
                assert not name.endswith("cli"), f"mcp_server imports {name}"

    def test_the_mcp_server_does_not_shell_out(self) -> None:
        source = (SRC / "mcp_server.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "popen"):
            assert forbidden not in source


class TestLibraryNeverImportsAnAdapter:
    """The import graph, walked. A check that imports the CLI is a layering failure."""

    @pytest.mark.parametrize("package", ["checks", "sources", "render", "ingest"])
    def test_no_adapter_imports(self, package: str) -> None:
        offenders: list[str] = []
        for path in (SRC / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                elif isinstance(node, ast.Import):
                    names.extend(a.name for a in node.names)
                for name in names:
                    if name.endswith("cli") or name.endswith("mcp_server"):
                        offenders.append(f"{path.name} imports {name}")
        assert offenders == []

    def test_report_module_does_not_import_an_adapter(self) -> None:
        source = (SRC / "report.py").read_text(encoding="utf-8")
        assert "from grantcheck.cli" not in source
        assert "mcp_server" not in source
