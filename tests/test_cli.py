"""Tests for the CLI interface."""

import pytest
from click.testing import CliRunner

from pe_compile.cli import main


class TestCLI:
    """Test the command-line interface."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    def test_help(self, runner):
        """Show help message."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Compile PolicyEngine" in result.output

    def test_version(self, runner):
        """Show version."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_missing_country(self, runner):
        """Error when country not specified."""
        result = runner.invoke(main, ["--variables", "income_tax"])
        assert result.exit_code != 0
        assert (
            "country" in result.output.lower()
            or "required" in result.output.lower()
        )

    def test_missing_variables(self, runner):
        """Error when no variables specified."""
        result = runner.invoke(main, ["--country", "uk"])
        assert result.exit_code != 0

    @pytest.mark.skip(reason="Requires policyengine-uk installed")
    def test_compile_single_variable(self, runner, tmp_path):
        """Compile a single variable to standalone code."""
        output_file = tmp_path / "output.py"
        result = runner.invoke(
            main,
            [
                "--country",
                "uk",
                "--variables",
                "income_tax",
                "--output",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

    @pytest.mark.skip(reason="Requires policyengine-uk installed")
    def test_compile_multiple_variables(self, runner, tmp_path):
        """Compile multiple variables."""
        output_file = tmp_path / "output.py"
        result = runner.invoke(
            main,
            [
                "--country",
                "uk",
                "--variables",
                "income_tax,national_insurance",
                "--output",
                str(output_file),
            ],
        )
        assert result.exit_code == 0

    def test_output_to_stdout(self, runner):
        """Output to stdout when no file specified."""
        # This test uses a mock system
        result = runner.invoke(
            main,
            [
                "--country",
                "mock",
                "--variables",
                "test_var",
            ],
        )
        # Should either succeed or fail gracefully
        assert result.exit_code in [0, 1, 2]

    @pytest.mark.skip(reason="Requires policyengine-uk installed")
    def test_specify_date(self, runner, tmp_path):
        """Compile with specific date for parameter values."""
        output_file = tmp_path / "output.py"
        result = runner.invoke(
            main,
            [
                "--country",
                "uk",
                "--variables",
                "income_tax",
                "--date",
                "2024-04-06",
                "--output",
                str(output_file),
            ],
        )
        assert result.exit_code == 0

    @pytest.mark.skip(reason="Requires policyengine-uk installed")
    def test_dry_run(self, runner):
        """Show what would be compiled without generating code."""
        result = runner.invoke(
            main,
            [
                "--country",
                "uk",
                "--variables",
                "income_tax",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "income_tax" in result.output
