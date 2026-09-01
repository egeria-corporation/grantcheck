"""MCP adapter. Zero business logic.

Every tool here resolves to :func:`grantcheck.report.build_report` — the same function the
command-line interface calls. It does not shell out to the CLI and it does not reimplement
a check, which is what makes it structurally impossible for the two surfaces to disagree.

Two things this file is careful about, because the consumer is a language model rather than
a person:

- **Every tool result carries its vintages in-band.** A model that quotes this tool has to
  be able to attribute the answer without making a second call, or it will quote a number
  with no date attached.
- **Every tool description carries the disclosure.** The model needs to know, at the point
  of deciding to use a result, that it is informational and not an eligibility
  determination.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from grantcheck import __version__, explanations
from grantcheck.ein import InvalidEIN
from grantcheck.models import DISCLOSURE
from grantcheck.render import markdown
from grantcheck.report import build_report
from grantcheck.sources.index import IndexClient, IndexUnavailable

INSTRUCTIONS = f"""
grantcheck reports whether a United States nonprofit is mechanically ready to apply for
federal grants, from public IRS data. Every fact carries the dataset it came from and the
date that dataset was published.

When you quote anything from these tools, quote the vintage with it. Every result includes
the dates in-band so you do not need a second call.

{DISCLOSURE}
""".strip()

_DISCLAIMER = f"Results are informational only. {DISCLOSURE}"


def _client() -> IndexClient:
    return IndexClient()


def build_server() -> MCPServer:
    """Construct the server. Separated from `serve` so tests can drive it in-process."""
    server = MCPServer(
        name="grantcheck",
        version=__version__,
        instructions=INSTRUCTIONS,
    )

    @server.tool(
        name="check_readiness",
        description=(
            "Check whether a US nonprofit is mechanically ready to apply for federal "
            "grants, by Employer Identification Number (EIN). Returns every check with its "
            "source and publication date, plus a Markdown summary you can quote directly. "
            "Pass uei to pin the SAM.gov registration when the inferred match is wrong. "
            f"{_DISCLAIMER}"
        ),
    )
    def check_readiness(ein: str, uei: str | None = None) -> dict[str, Any]:
        client = _client()
        try:
            report = build_report(ein, client=client, uei=uei)
        except InvalidEIN as exc:
            return {"error": "invalid_ein", "message": str(exc)}
        except IndexUnavailable as exc:
            return {"error": "index_unavailable", "message": str(exc)}
        finally:
            client.close()

        return {
            "report": report.to_dict(),
            "summary_markdown": markdown.render(report),
            "disclosure": report.disclosure,
        }

    @server.tool(
        name="find_ein",
        description=(
            "Find candidate organizations by name, to get an EIN for check_readiness. "
            "Returns up to ten candidates with EIN, name, city, and state. This searches "
            "only the locally cached portion of the index, so it is a lookup aid rather "
            "than a directory, and it may return nothing on a cold cache. "
            f"{_DISCLAIMER}"
        ),
    )
    def find_ein(name: str, state: str | None = None) -> dict[str, Any]:
        client = _client()
        try:
            rows = client.search_by_name(name, state=state, limit=10)
            manifest = client.manifest()
        except IndexUnavailable as exc:
            return {"error": "index_unavailable", "message": str(exc)}
        finally:
            client.close()

        return {
            "candidates": [
                {
                    "ein": f"{r['ein'][:2]}-{r['ein'][2:]}",
                    "name": r.get("name"),
                    "city": r.get("city"),
                    "state": r.get("state"),
                }
                for r in rows
            ],
            "vintages": manifest.datasets,
            "note": (
                "Searched the locally cached shards only. An organization absent from these "
                "results may simply be in a part of the index not cached yet."
            ),
            "disclosure": DISCLOSURE,
        }

    @server.tool(
        name="explain_check",
        description=(
            "Explain what one of grantcheck's checks means, why it can stop a federal "
            "application, and what to do about it. Pass the check id from a "
            "check_readiness result. "
            f"{_DISCLAIMER}"
        ),
    )
    def explain_check(check_id: str) -> dict[str, Any]:
        text = explanations.get(check_id)
        if text is None:
            return {
                "error": "unknown_check_id",
                "message": f"No explainer for {check_id!r}.",
                "available": explanations.available(),
            }
        return {"check_id": check_id, "explanation": text, "disclosure": DISCLOSURE}

    @server.tool(
        name="dataset_vintages",
        description=(
            "Report which public datasets the current index was built from and the date "
            "each one was published. Use this to state how fresh an answer is. "
            f"{_DISCLAIMER}"
        ),
    )
    def dataset_vintages() -> dict[str, Any]:
        client = _client()
        try:
            manifest = client.manifest()
        except IndexUnavailable as exc:
            return {"error": "index_unavailable", "message": str(exc)}
        finally:
            client.close()

        return {
            "index_vintage": manifest.vintage,
            "built_at": manifest.built_at,
            "from_cache": manifest.from_cache,
            "datasets": manifest.datasets,
            "disclosure": DISCLOSURE,
        }

    return server


def serve() -> None:
    """Run the server on stdio. This is what `grantcheck mcp` invokes."""
    build_server().run(transport="stdio")


def tool_payload(result: Any) -> dict[str, Any]:
    """Normalize a tool result to a dict, for tests and for callers holding raw content."""
    if isinstance(result, dict):
        return result
    return json.loads(result)
