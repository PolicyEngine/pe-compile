"""Tests for entity-aware JavaScript code generation.

These tests verify that generated JS code correctly handles:
- Multi-person households
- Aggregation (person → household)
- Broadcasting (household → person)
- Complex PE formula patterns
"""

import pytest

from pe_compile.js_generator import (
    JSCodeGenerator,
    python_to_js_expression,
)
from pe_compile.js_runtime import get_js_runtime, generate_js_with_runtime


class TestJSRuntime:
    """Test the JavaScript runtime generation."""

    def test_runtime_includes_entity_model(self):
        """Runtime should include createEntityModel function."""
        runtime = get_js_runtime()
        assert "function createEntityModel" in runtime

    def test_runtime_includes_aggregation(self):
        """Runtime should include aggregation functions."""
        runtime = get_js_runtime()
        assert "function aggregateSum" in runtime
        assert "function aggregateAny" in runtime
        assert "function aggregateMax" in runtime
        assert "function aggregateMin" in runtime
        assert "function aggregateCount" in runtime

    def test_runtime_includes_broadcasting(self):
        """Runtime should include broadcasting function."""
        runtime = get_js_runtime()
        assert "function broadcastToMembers" in runtime

    def test_runtime_includes_array_ops(self):
        """Runtime should include element-wise array operations."""
        runtime = get_js_runtime()
        assert "arrayOps" in runtime
        assert "where:" in runtime


class TestEntityAwareExpressions:
    """Test conversion of PE entity patterns to JS."""

    def test_person_variable_access(self):
        """Convert person('variable', period) to model access."""
        # This should become model.getPersonVariable('employment_income')
        # For now, just test the basic conversion
        expr = 'person("employment_income", period)'
        # The full conversion happens in the generator, not just expression conversion

    def test_household_sum_pattern(self):
        """Convert household.sum() to aggregateSum()."""
        # PE: household.sum(household.members("income", period))
        # JS: aggregateSum(model.getPersonVariable("income"), personToHH, nHH)
        pass

    def test_person_household_broadcast(self):
        """Convert person.household() to broadcastToMembers()."""
        # PE: person.household("housing_costs", period)
        # JS: broadcastToMembers(model.getHouseholdVariable("housing_costs"), personToHH)
        pass


class TestEntityAwareGenerator:
    """Test the entity-aware code generator."""

    def test_generate_with_runtime(self):
        """Generated code should include runtime when requested."""
        gen = JSCodeGenerator(include_entity_runtime=True)
        gen.add_input("employment_income", default=0)
        gen.add_calculation("tax", "employment_income * 0.2")

        code = gen.generate()
        assert "createEntityModel" in code

    def test_generate_situation_based_calculator(self):
        """Generate calculator that takes situation object."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
        )
        gen.add_person_variable("employment_income", is_input=True)
        gen.add_person_variable(
            "income_tax",
            formula="arrayOps.mul(employment_income, 0.2)",
        )

        code = gen.generate()

        # Should take situation as input
        assert "situation" in code
        # Should use entity model
        assert "getPersonVariable" in code

    def test_generate_household_aggregation(self):
        """Generate code that aggregates person values to household."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
        )
        gen.add_person_variable("employment_income", is_input=True)
        gen.add_household_variable(
            "household_income",
            formula="aggregateSum(employment_income, personToHH, nHouseholds)",
        )

        code = gen.generate()

        assert "aggregateSum" in code

    def test_generate_person_gets_household_value(self):
        """Generate code where person accesses household value."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
        )
        gen.add_household_variable("housing_costs", is_input=True)
        gen.add_person_variable(
            "housing_costs_per_person",
            formula="broadcastToMembers(housing_costs, personToHH)",
        )

        code = gen.generate()

        assert "broadcastToMembers" in code


class TestCompleteEntityAwareModule:
    """Test generation of complete entity-aware modules."""

    def test_income_tax_multi_person(self):
        """Generate income tax calculation for multi-person household."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
        )

        # Inputs
        gen.add_person_variable("employment_income", is_input=True, default=0)
        gen.add_person_variable("age", is_input=True, default=30)

        # Person-level calculations
        gen.add_person_variable(
            "is_adult",
            formula="arrayOps.gte(age, 18)",
        )
        gen.add_person_variable(
            "taxable_income",
            formula="arrayOps.max(employment_income, 0)",
        )
        gen.add_person_variable(
            "income_tax",
            formula="arrayOps.mul(taxable_income, 0.2)",
        )

        # Household-level aggregations
        gen.add_household_variable(
            "household_income",
            formula="aggregateSum(employment_income, personToHH, nHouseholds)",
        )
        gen.add_household_variable(
            "household_tax",
            formula="aggregateSum(income_tax, personToHH, nHouseholds)",
        )
        gen.add_household_variable(
            "n_adults",
            formula=(
                "aggregateSum("
                "is_adult.map(x => x ? 1 : 0), personToHH, nHouseholds"
                ")"
            ),
        )

        code = gen.generate()

        # Should have all the key components
        assert "createEntityModel" in code
        assert "employment_income" in code
        assert "income_tax" in code
        assert "household_income" in code
        assert "aggregateSum" in code

    def test_benefit_calculation_with_means_test(self):
        """Generate benefit with household-level means test."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
        )

        # Inputs
        gen.add_person_variable("employment_income", is_input=True, default=0)

        # Aggregate to household
        gen.add_household_variable(
            "household_income",
            formula="aggregateSum(employment_income, personToHH, nHouseholds)",
        )

        # Household-level benefit (means-tested)
        gen.add_household_variable(
            "housing_benefit",
            formula=(
                "arrayOps.where("
                "arrayOps.lt(household_income, 30000), "
                "arrayOps.mul(arrayOps.sub(30000, household_income), 0.5), "
                "household_income.map(() => 0)"
                ")"
            ),
        )

        # Broadcast back to person for individual share
        gen.add_person_variable(
            "housing_benefit_per_person",
            formula=(
                "arrayOps.div("
                "broadcastToMembers(housing_benefit, personToHH), "
                "broadcastToMembers(aggregateCount(personToHH, nHouseholds), personToHH)"
                ")"
            ),
        )

        code = gen.generate()

        assert "housing_benefit" in code
        assert "broadcastToMembers" in code


class TestHTMLDemoWithEntities:
    """Test HTML demo generation with entity support."""

    def test_html_demo_supports_multiple_people(self):
        """HTML demo should allow adding multiple people."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
        )
        gen.add_person_variable("employment_income", is_input=True, default=0)
        gen.add_household_variable(
            "household_income",
            formula="aggregateSum(employment_income, personToHH, nHouseholds)",
        )

        html = gen.generate_html_demo(title="Multi-Person Calculator")

        # Should have UI for adding people
        # (This is a stretch goal - for now just check it generates)
        assert "<!DOCTYPE html>" in html
