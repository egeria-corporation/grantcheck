"""Command-line adapter.

Zero business logic lives here. Every command resolves to a library call and a renderer.
A rule implemented inside a Click callback is a bug — see ``prompts/01-build-core.md``
section 3, constraint 3.
"""

from __future__ import annotations

import sys

import click

from grantcheck import __version__
from grantcheck.ein import InvalidEIN
from grantcheck.models import EXIT_ERROR
from grantcheck.render import json as json_render
from grantcheck.render import markdown, table
from grantcheck.report import build_report
from grantcheck.sources.index import IndexClient, IndexUnavailable

EXIT_CODE_HELP = """
\b
Exit codes:
  0  ready       — nothing observed that would stop a submission
  1  error       — bad input, or the index could not be reached with no cache
  2  blocked     — at least one blocking check failed
  3  attention   — warnings only
  4  not found   — the EIN is not in the published index

These exist so a whole client roster can be checked from a script.
"""


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog=EXIT_CODE_HELP,
)
@click.version_option(__version__, "-V", "--version", prog_name="grantcheck")
@click.option("--ein", help="The EIN to check, with or without the hyphen.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "markdown", "json"]),
    default="table",
    show_default=True,
    help="table for a terminal, markdown to paste into a memo, json for a machine.",
)
@click.option(
    "--uei",
    help=(
        "Pin the SAM.gov registration by Unique Entity ID, skipping name matching. "
        "Use this whenever the inferred match is wrong."
    ),
)
@click.pass_context
def main(ctx: click.Context, ein: str | None, uei: str | None, output_format: str) -> None:
    """Check whether an organization is mechanically ready to apply for federal grants.

    Reports observable facts from public IRS data, each with its source and publication
    date. It is not an eligibility determination.
    """
    if ctx.invoked_subcommand is not None:
        return
    if ein is None:
        click.echo(ctx.get_help())
        return
    ctx.exit(_report(ein, uei=uei, output_format=output_format))


# Markdown and JSON are file formats: they get redirected into a document, committed, or
# posted to an API, and they are UTF-8 by definition. On Windows a redirected stdout
# defaults to the ANSI code page, so `grantcheck --format markdown > report.md` wrote
# cp1252 and produced a file that is not valid UTF-8 anywhere else.
#
# Reconfiguring sys.stdout is not enough: click caches its own text wrapper around the
# original stream on first use, so the characters are already replaced by the time the
# encoding changes. Writing encoded bytes to the underlying buffer is unambiguous.
#
# The table format is deliberately NOT forced. It is terminal output, and the renderer
# already adapts to whatever the terminal can actually display.
FILE_FORMATS = {"markdown", "json"}


def _write_utf8(text: str) -> None:
    """Write text to stdout as UTF-8 regardless of the platform default."""
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        # A captured stream, as in tests. It is already text and already unicode-safe.
        click.echo(text, nl=False)
        return
    buffer.write(text.encode("utf-8"))
    buffer.flush()


RENDERERS = {
    "table": lambda r: table.render(r),
    "markdown": markdown.render,
    "json": json_render.render,
}


def _report(ein: str, *, uei: str | None = None, output_format: str = "table") -> int:
    """Build and print one report. Returns the process exit code."""
    client = IndexClient()
    try:
        report = build_report(ein, client=client, uei=uei)
    except InvalidEIN as exc:
        click.echo(f"Error: {exc}", err=True)
        return EXIT_ERROR
    except IndexUnavailable as exc:
        click.echo(f"Error: {exc}", err=True)
        return EXIT_ERROR
    finally:
        client.close()

    rendered = RENDERERS[output_format](report)
    if output_format in FILE_FORMATS:
        _write_utf8(rendered)
    else:
        click.echo(rendered, nl=False)
    return report.exit_code


@main.command("cache")
@click.argument("action", type=click.Choice(["info", "clear"]))
def cache(action: str) -> None:
    """Show or remove locally cached data files."""
    client = IndexClient()
    if action == "clear":
        freed = client.cache_clear()
        click.echo(f"Removed {freed / 1048576:.1f} MB from {client.cache}")
        return

    info = client.cache_info()
    click.echo(f"Cache directory: {info['cache_dir']}")
    if not info["vintages"]:
        click.echo("Nothing cached yet.")
        return
    for vintage, entry in sorted(info["vintages"].items(), reverse=True):
        click.echo(
            f"  {vintage}: {entry['shards']} data file(s), {entry['bytes'] / 1048576:.1f} MB"
        )
    click.echo(f"Total: {info['total_bytes'] / 1048576:.1f} MB")


def cli() -> None:  # pragma: no cover - console entry point
    sys.exit(main.main(standalone_mode=False) or 0)


if __name__ == "__main__":  # pragma: no cover
    main()
