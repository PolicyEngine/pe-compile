"""Tests for dependency graph extraction from PolicyEngine variables."""

import pytest

from pe_compile.graph import (
    DependencyGraph,
    build_dependency_graph,
    extract_dependencies_from_formula,
)


class TestExtractDependenciesFromFormula:
    """Test extracting variable and parameter dependencies from formulas."""

    def test_simple_variable_reference(self):
        """Extract a single variable reference."""
        formula_source = """
def formula(person, period):
    return person("employment_income", period)
"""
        deps = extract_dependencies_from_formula(formula_source)
        assert "employment_income" in deps.variables
        assert len(deps.parameters) == 0

    def test_multiple_variable_references(self):
        """Extract multiple variable references."""
        formula_source = """
def formula(person, period):
    income = person("employment_income", period)
    benefits = person("child_benefit", period)
    return income + benefits
"""
        deps = extract_dependencies_from_formula(formula_source)
        assert "employment_income" in deps.variables
        assert "child_benefit" in deps.variables

    def test_parameter_reference(self):
        """Extract parameter references."""
        formula_source = """
def formula(person, period, parameters):
    rate = parameters(period).gov.hmrc.income_tax.rates.basic
    return person("taxable_income", period) * rate
"""
        deps = extract_dependencies_from_formula(formula_source)
        assert "taxable_income" in deps.variables
        assert "gov.hmrc.income_tax.rates.basic" in deps.parameters

    def test_household_entity_reference(self):
        """Extract references through household entity."""
        formula_source = """
def formula(household, period):
    return household("household_income", period)
"""
        deps = extract_dependencies_from_formula(formula_source)
        assert "household_income" in deps.variables

    def test_sum_aggregation(self):
        """Extract references with sum aggregation."""
        formula_source = """
def formula(household, period):
    return household.sum(household.members("employment_income", period))
"""
        deps = extract_dependencies_from_formula(formula_source)
        assert "employment_income" in deps.variables

    def test_where_clause(self):
        """Extract references in where clauses."""
        formula_source = """
def formula(person, period):
    is_adult = person("is_adult", period)
    income = person("employment_income", period)
    return where(is_adult, income, 0)
"""
        deps = extract_dependencies_from_formula(formula_source)
        assert "is_adult" in deps.variables
        assert "employment_income" in deps.variables

    def test_nested_parameter_path(self):
        """Extract deeply nested parameter paths."""
        formula_source = """
def formula(person, period, parameters):
    p = parameters(period)
    threshold = p.gov.dwp.universal_credit.elements.child.first.amount
    return threshold
"""
        deps = extract_dependencies_from_formula(formula_source)
        assert (
            "gov.dwp.universal_credit.elements.child.first.amount"
            in deps.parameters
        )


class TestDependencyGraph:
    """Test the dependency graph data structure."""

    def test_empty_graph(self):
        """Create an empty dependency graph."""
        graph = DependencyGraph()
        assert len(graph.variables) == 0
        assert len(graph.parameters) == 0

    def test_add_variable(self):
        """Add a variable to the graph."""
        graph = DependencyGraph()
        graph.add_variable(
            name="income_tax",
            dependencies=["taxable_income"],
            formula_source="def formula(p, period): ...",
        )
        assert "income_tax" in graph.variables
        assert "taxable_income" in graph.variables["income_tax"].dependencies

    def test_get_transitive_dependencies(self):
        """Get all transitive dependencies of a variable."""
        graph = DependencyGraph()
        graph.add_variable("c", dependencies=["b"], formula_source="...")
        graph.add_variable("b", dependencies=["a"], formula_source="...")
        graph.add_variable("a", dependencies=[], formula_source="...")

        deps = graph.get_transitive_dependencies("c")
        assert deps == {"a", "b"}

    def test_get_transitive_dependencies_with_cycle(self):
        """Handle circular dependencies gracefully."""
        graph = DependencyGraph()
        graph.add_variable("a", dependencies=["b"], formula_source="...")
        graph.add_variable("b", dependencies=["a"], formula_source="...")

        # Should not infinite loop
        deps = graph.get_transitive_dependencies("a")
        assert "b" in deps

    def test_topological_sort(self):
        """Sort variables in dependency order."""
        graph = DependencyGraph()
        graph.add_variable("c", dependencies=["b"], formula_source="...")
        graph.add_variable("b", dependencies=["a"], formula_source="...")
        graph.add_variable("a", dependencies=[], formula_source="...")

        sorted_vars = graph.topological_sort(["c"])
        assert sorted_vars.index("a") < sorted_vars.index("b")
        assert sorted_vars.index("b") < sorted_vars.index("c")


class TestBuildDependencyGraph:
    """Test building dependency graph from a country tax-benefit system."""

    @pytest.fixture
    def mock_variable_class(self):
        """Create a mock variable class for testing."""

        class MockVariable:
            __name__ = "test_variable"
            entity = type("Entity", (), {"key": "person"})()
            definition_period = "year"
            value_type = float
            default_value = 0

            def formula(self, person, period):
                return person("other_variable", period)

        return MockVariable

    def test_build_from_single_variable(self, mock_variable_class):
        """Build graph from a single variable."""
        variables = {"test_variable": mock_variable_class}

        graph = build_dependency_graph(variables)
        assert "test_variable" in graph.variables

    def test_extract_formula_source(self, mock_variable_class):
        """Extract the formula source code."""
        variables = {"test_variable": mock_variable_class}

        graph = build_dependency_graph(variables)
        var_info = graph.variables["test_variable"]
        assert "other_variable" in var_info.formula_source
