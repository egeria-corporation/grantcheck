"""M0 demo: the console entry point exists and reports a version."""

from click.testing import CliRunner

import grantcheck
from grantcheck.cli import main


def test_version_is_reported() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "grantcheck" in result.output


def test_package_exposes_a_version() -> None:
    assert grantcheck.__version__
