"""Tests for reform support in pe-compile."""

import pytest
from click.testing import CliRunner

from pe_compile.cli import main
from pe_compile.reform import (apply_reform_to_parameters, parse_reform_dict,
                               parse_reform_json)


class TestParseReformJson:
    """Test parsing reform JSON strings."""

    def test_simple_parameter_override(self):
        """Parse a simple parameter value override."""
        reform_json = '{"gov.tax.rate": 0.25}'
        reform = parse_reform_json(reform_json)

        assert "gov.tax.rate" in reform
        assert reform["gov.tax.rate"] == 0.25

    def test_multiple_parameters(self):
        """Parse multiple parameter overrides."""
        reform_json = """{
            "gov.tax.basic_rate": 0.19,
            "gov.tax.higher_rate": 0.39,
            "gov.benefits.amount": 5000
        }"""
        reform = parse_reform_json(reform_json)

        assert reform["gov.tax.basic_rate"] == 0.19
        assert reform["gov.tax.higher_rate"] == 0.39
        assert reform["gov.benefits.amount"] == 5000

    def test_invalid_json(self):
        """Raise error for invalid JSON."""
        with pytest.raises(ValueError, match="Invalid reform JSON"):
            parse_reform_json("not valid json")

    def test_empty_reform(self):
        """Handle empty reform dict."""
        reform = parse_reform_json("{}")
        assert reform == {}


class TestParseReformDict:
    """Test parsing reform dictionaries (PE format)."""

    def test_simple_reform_dict(self):
        """Parse PolicyEngine-style reform dict."""
        reform_dict = {
            "gov.tax.rate": {
                "2024-01-01": 0.25,
            }
        }
        reform = parse_reform_dict(reform_dict, year=2024)

        assert reform["gov.tax.rate"] == 0.25

    def test_reform_with_multiple_years(self):
        """Select correct year from multi-year reform."""
        reform_dict = {
            "gov.tax.rate": {
                "2023-01-01": 0.20,
                "2024-01-01": 0.25,
                "2025-01-01": 0.30,
            }
        }

        reform_2023 = parse_reform_dict(reform_dict, year=2023)
        reform_2024 = parse_reform_dict(reform_dict, year=2024)
        reform_2025 = parse_reform_dict(reform_dict, year=2025)

        assert reform_2023["gov.tax.rate"] == 0.20
        assert reform_2024["gov.tax.rate"] == 0.25
        assert reform_2025["gov.tax.rate"] == 0.30

    def test_reform_year_not_found_uses_latest_before(self):
        """Use latest value before requested year."""
        reform_dict = {
            "gov.tax.rate": {
                "2020-01-01": 0.20,
                "2023-01-01": 0.25,
            }
        }
        # 2024 should use 2023 value (latest before)
        reform = parse_reform_dict(reform_dict, year=2024)
        assert reform["gov.tax.rate"] == 0.25


class TestApplyReformToParameters:
    """Test applying reforms to parameter dictionaries."""

    def test_override_existing_parameter(self):
        """Override an existing parameter value."""
        base_params = {
            "gov.tax.rate": 0.20,
            "gov.tax.threshold": 12570,
        }
        reform = {"gov.tax.rate": 0.25}

        result = apply_reform_to_parameters(base_params, reform)

        assert result["gov.tax.rate"] == 0.25
        assert result["gov.tax.threshold"] == 12570  # unchanged

    def test_add_new_parameter(self):
        """Add a new parameter that wasn't in base."""
        base_params = {"gov.tax.rate": 0.20}
        reform = {"gov.tax.new_param": 100}

        result = apply_reform_to_parameters(base_params, reform)

        assert result["gov.tax.rate"] == 0.20
        assert result["gov.tax.new_param"] == 100

    def test_empty_reform(self):
        """Empty reform returns base unchanged."""
        base_params = {"gov.tax.rate": 0.20}
        reform = {}

        result = apply_reform_to_parameters(base_params, reform)

        assert result == base_params

    def test_original_not_modified(self):
        """Base params dict is not modified in place."""
        base_params = {"gov.tax.rate": 0.20}
        reform = {"gov.tax.rate": 0.25}

        apply_reform_to_parameters(base_params, reform)

        assert base_params["gov.tax.rate"] == 0.20  # unchanged


class TestCLIReformOption:
    """Test the --reform CLI option."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_reform_option_help(self, runner):
        """Reform option appears in help."""
        result = runner.invoke(main, ["--help"])
        assert "--reform" in result.output

    def test_reform_with_mock_system(self, runner):
        """Apply reform to mock system."""
        result = runner.invoke(
            main,
            [
                "-c",
                "mock",
                "-v",
                "test_var",
                "--reform",
                '{"mock.param": 100}',
            ],
        )
        # Should complete without error
        assert result.exit_code == 0

    @pytest.mark.skip(reason="Requires policyengine-uk installed")
    def test_reform_with_uk_system(self, runner, tmp_path):
        """Apply reform to UK income tax."""
        output_file = tmp_path / "reformed.py"
        result = runner.invoke(
            main,
            [
                "-c",
                "uk",
                "-v",
                "income_tax",
                "--year",
                "2024",
                "--reform",
                '{"gov.hmrc.income_tax.rates.uk.basic": 0.19}',
                "-o",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

        # Check the generated code has the reformed value
        code = output_file.read_text()
        assert "0.19" in code
