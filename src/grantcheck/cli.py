"""Command-line adapter.

Zero business logic lives here. Every command resolves to a library call and a renderer.
A rule implemented inside a Click callback is a bug — see ``prompts/01-build-core.md``
section 3, constraint 3.
"""

import click

from grantcheck import __version__


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "-V", "--version", prog_name="grantcheck")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Check whether an organization is mechanically ready to apply for federal grants.

    Reports observable facts from public IRS and SAM.gov data, each with its source and
    publication date. It is not an eligibility determination.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


if __name__ == "__main__":  # pragma: no cover
    main()
