"""Federal grant readiness check by EIN.

Everything a caller needs is reachable from :func:`grantcheck.report.build_report`. The
command-line interface and the MCP server are both thin adapters over it — see
``prompts/01-build-core.md`` section 4.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("grantcheck")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
