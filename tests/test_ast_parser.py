"""Tests for AST-based formula parsing."""

import pytest

from pe_compile.ast_parser import (FormulaAnalyzer, extract_add_variables,
                                   extract_parameter_references,
                                   extract_variable_references,
                                   extract_where_conditions)


class TestExtractVariableReferences:
    """Test extracting variable references from formulas."""

    def test_simple_variable_call(self):
        """Extract variable from person('var', period)."""
        source = """
def formula(person, period):
    income = person("employment_income", period)
    return income
"""
        refs = extract_variable_references(source)
        assert "employment_income" in refs

    def test_multiple_variable_calls(self):
        """Extract multiple variable references."""
        source = """
def formula(person, period):
    emp = person("employment_income", period)
    self_emp = person("self_employment_income", period)
    return emp + self_emp
"""
        refs = extract_variable_references(source)
        assert "employment_income" in refs
        assert "self_employment_income" in refs

    def test_add_function(self):
        """Extract variables from add() calls."""
        source = """
def formula(person, period):
    return add(person, period, ["employment_income", "self_employment_income"])
"""
        refs = extract_variable_references(source)
        assert "employment_income" in refs
        assert "self_employment_income" in refs

    def test_household_reference(self):
        """Extract variables from entity hierarchy calls."""
        source = """
def formula(person, period):
    hh_income = person.household("household_income", period)
    return hh_income
"""
        refs = extract_variable_references(source)
        assert "household_income" in refs

    def test_benunit_reference(self):
        """Extract variables from benefit unit calls."""
        source = """
def formula(person, period):
    bu_income = person.benunit("benefit_unit_income", period)
    return bu_income
"""
        refs = extract_variable_references(source)
        assert "benefit_unit_income" in refs

    def test_tax_unit_reference(self):
        """Extract variables from tax unit calls."""
        source = """
def formula(person, period):
    tu_income = person.tax_unit("tax_unit_income", period)
    return tu_income
"""
        refs = extract_variable_references(source)
        assert "tax_unit_income" in refs

    def test_members_reference(self):
        """Extract variables from .members() calls."""
        source = """
def formula(household, period):
    return household.sum(household.members("employment_income", period))
"""
        refs = extract_variable_references(source)
        assert "employment_income" in refs


class TestExtractParameterReferences:
    """Test extracting parameter references from formulas."""

    def test_simple_parameter(self):
        """Extract parameter from parameters(period).path."""
        source = """
def formula(person, period):
    rate = parameters(period).gov.hmrc.income_tax.rates.uk.basic
    return income * rate
"""
        refs = extract_parameter_references(source)
        assert "gov.hmrc.income_tax.rates.uk.basic" in refs

    def test_parameter_with_alias(self):
        """Extract parameter when using p = parameters(period)."""
        source = """
def formula(person, period):
    p = parameters(period)
    rate = p.gov.hmrc.income_tax.rates.uk.basic
    threshold = p.gov.hmrc.income_tax.allowances.personal_allowance
    return max(0, income - threshold) * rate
"""
        refs = extract_parameter_references(source)
        assert "gov.hmrc.income_tax.rates.uk.basic" in refs
        assert "gov.hmrc.income_tax.allowances.personal_allowance" in refs

    def test_nested_parameter_access(self):
        """Extract deeply nested parameters."""
        source = """
def formula(person, period):
    p = parameters(period)
    amount = p.gov.dwp.benefits.universal_credit.standard_allowance.amount
    return amount
"""
        refs = extract_parameter_references(source)
        assert (
            "gov.dwp.benefits.universal_credit.standard_allowance.amount"
            in refs
        )


class TestExtractAddVariables:
    """Test extracting variables from add() function calls."""

    def test_add_with_list(self):
        """Extract from add(entity, period, [vars])."""
        source = """
def formula(person, period):
    return add(person, period, ["var1", "var2", "var3"])
"""
        vars = extract_add_variables(source)
        assert vars == ["var1", "var2", "var3"]

    def test_add_with_variable_list(self):
        """Handle add with variable containing the list."""
        source = """
def formula(person, period):
    income_sources = ["employment_income", "pension_income"]
    return add(person, period, income_sources)
"""
        # Should still find the string literals in the list
        vars = extract_add_variables(source)
        assert "employment_income" in vars
        assert "pension_income" in vars


class TestExtractWhereConditions:
    """Test extracting conditions from where() calls."""

    def test_simple_where(self):
        """Extract where condition components."""
        source = """
def formula(person, period):
    income = person("income", period)
    return where(income > 50000, income * 0.4, income * 0.2)
"""
        conditions = extract_where_conditions(source)
        assert len(conditions) >= 1

    def test_nested_where(self):
        """Handle nested where conditions."""
        source = """
def formula(person, period):
    income = person("income", period)
    return where(
        income > 125140,
        income * 0.45,
        where(income > 50270, income * 0.4, income * 0.2)
    )
"""
        conditions = extract_where_conditions(source)
        assert len(conditions) >= 2


class TestFormulaAnalyzer:
    """Test the complete formula analyzer."""

    def test_analyze_simple_formula(self):
        """Analyze a simple formula."""
        source = """
def formula(person, period):
    income = person("employment_income", period)
    rate = parameters(period).gov.tax.rate
    return income * rate
"""
        analyzer = FormulaAnalyzer(source)

        assert "employment_income" in analyzer.variables
        assert "gov.tax.rate" in analyzer.parameters

    def test_analyze_complex_formula(self):
        """Analyze a complex formula with multiple patterns."""
        source = """
def formula(person, period):
    p = parameters(period)

    employment = person("employment_income", period)
    self_emp = person("self_employment_income", period)
    total = employment + self_emp

    allowance = p.gov.hmrc.income_tax.allowances.personal_allowance
    rate = p.gov.hmrc.income_tax.rates.uk.basic

    taxable = max(0, total - allowance)
    return taxable * rate
"""
        analyzer = FormulaAnalyzer(source)

        assert "employment_income" in analyzer.variables
        assert "self_employment_income" in analyzer.variables
        assert (
            "gov.hmrc.income_tax.allowances.personal_allowance"
            in analyzer.parameters
        )
        assert "gov.hmrc.income_tax.rates.uk.basic" in analyzer.parameters

    def test_analyze_add_formula(self):
        """Analyze formula using add()."""
        source = """
def formula(person, period):
    return add(person, period, [
        "employment_income",
        "self_employment_income",
        "pension_income",
    ])
"""
        analyzer = FormulaAnalyzer(source)

        assert "employment_income" in analyzer.variables
        assert "self_employment_income" in analyzer.variables
        assert "pension_income" in analyzer.variables

    def test_analyze_entity_hierarchy(self):
        """Analyze formula with entity hierarchy references."""
        source = """
def formula(person, period):
    personal = person("employment_income", period)
    household = person.household("household_benefits", period)
    return personal + household
"""
        analyzer = FormulaAnalyzer(source)

        assert "employment_income" in analyzer.variables
        assert "household_benefits" in analyzer.variables

    def test_get_entity_type(self):
        """Detect entity type from formula signature."""
        person_source = """
def formula(person, period):
    return person("income", period)
"""
        household_source = """
def formula(household, period):
    return household("housing_costs", period)
"""
        analyzer_person = FormulaAnalyzer(person_source)
        analyzer_hh = FormulaAnalyzer(household_source)

        assert analyzer_person.entity_type == "person"
        assert analyzer_hh.entity_type == "household"
