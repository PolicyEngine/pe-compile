"""Tests for entity hierarchy model in generated code.

PolicyEngine has complex entity relationships:
- Households contain people
- Tax units contain people (US)
- Benefit units contain people (UK)
- Variables are defined at specific entity levels
- Calculations can aggregate (person → household) or broadcast (household → person)
"""

import pytest

from pe_compile.entity_model import (
    EntityModel,
    Situation,
    aggregate_sum,
    aggregate_any,
    aggregate_max,
    aggregate_min,
    aggregate_count,
    broadcast_to_members,
    get_entity_index,
)


class TestSituation:
    """Test the Situation data structure."""

    def test_create_single_person_household(self):
        """Create a simple single-person household."""
        situation = Situation(
            people={
                "adult": {"employment_income": 50000, "age": 35},
            },
            households={
                "household": {"members": ["adult"]},
            },
        )

        assert len(situation.people) == 1
        assert len(situation.households) == 1
        assert situation.people["adult"]["employment_income"] == 50000

    def test_create_multi_person_household(self):
        """Create a household with multiple people."""
        situation = Situation(
            people={
                "adult1": {"employment_income": 50000, "age": 35},
                "adult2": {"employment_income": 30000, "age": 32},
                "child1": {"employment_income": 0, "age": 10},
            },
            households={
                "household": {"members": ["adult1", "adult2", "child1"]},
            },
        )

        assert len(situation.people) == 3
        assert len(situation.households["household"]["members"]) == 3

    def test_create_multiple_households(self):
        """Create multiple households."""
        situation = Situation(
            people={
                "person1": {"employment_income": 40000},
                "person2": {"employment_income": 60000},
            },
            households={
                "hh1": {"members": ["person1"]},
                "hh2": {"members": ["person2"]},
            },
        )

        assert len(situation.households) == 2


class TestEntityModel:
    """Test the EntityModel that powers calculations."""

    def test_get_person_variable(self):
        """Get a person-level variable as array."""
        model = EntityModel(
            people={
                "adult1": {"employment_income": 50000},
                "adult2": {"employment_income": 30000},
                "child1": {"employment_income": 0},
            },
            households={
                "hh": {"members": ["adult1", "adult2", "child1"]},
            },
        )

        incomes = model.get_person_variable("employment_income")
        assert list(incomes) == [50000, 30000, 0]

    def test_get_person_variable_with_default(self):
        """Get person variable with default for missing values."""
        model = EntityModel(
            people={
                "adult1": {"employment_income": 50000},
                "adult2": {},  # No income specified
            },
            households={
                "hh": {"members": ["adult1", "adult2"]},
            },
        )

        incomes = model.get_person_variable("employment_income", default=0)
        assert list(incomes) == [50000, 0]

    def test_get_household_variable(self):
        """Get a household-level variable."""
        model = EntityModel(
            people={"p1": {}, "p2": {}},
            households={
                "hh1": {"members": ["p1"], "housing_costs": 1000},
                "hh2": {"members": ["p2"], "housing_costs": 1500},
            },
        )

        costs = model.get_household_variable("housing_costs")
        assert list(costs) == [1000, 1500]

    def test_person_to_household_mapping(self):
        """Get mapping from person index to household index."""
        model = EntityModel(
            people={"p1": {}, "p2": {}, "p3": {}},
            households={
                "hh1": {"members": ["p1", "p2"]},
                "hh2": {"members": ["p3"]},
            },
        )

        # p1 and p2 are in hh1 (index 0), p3 is in hh2 (index 1)
        mapping = model.person_to_household_index()
        assert list(mapping) == [0, 0, 1]


class TestAggregation:
    """Test aggregation from person to household level."""

    def test_aggregate_sum(self):
        """Sum person values to household level."""
        person_values = [50000, 30000, 0]  # 3 people
        person_to_hh = [0, 0, 0]  # All in same household
        n_households = 1

        result = aggregate_sum(person_values, person_to_hh, n_households)
        assert list(result) == [80000]

    def test_aggregate_sum_multiple_households(self):
        """Sum across multiple households."""
        person_values = [50000, 30000, 40000]
        person_to_hh = [0, 0, 1]  # First two in hh0, third in hh1
        n_households = 2

        result = aggregate_sum(person_values, person_to_hh, n_households)
        assert list(result) == [80000, 40000]

    def test_aggregate_any(self):
        """Check if any person in household satisfies condition."""
        person_values = [True, False, True]
        person_to_hh = [0, 0, 1]
        n_households = 2

        result = aggregate_any(person_values, person_to_hh, n_households)
        assert list(result) == [True, True]

    def test_aggregate_any_none_true(self):
        """No person satisfies condition."""
        person_values = [False, False, True]
        person_to_hh = [0, 0, 1]
        n_households = 2

        result = aggregate_any(person_values, person_to_hh, n_households)
        assert list(result) == [False, True]

    def test_aggregate_max(self):
        """Get max person value per household."""
        person_values = [50000, 30000, 40000]
        person_to_hh = [0, 0, 1]
        n_households = 2

        result = aggregate_max(person_values, person_to_hh, n_households)
        assert list(result) == [50000, 40000]

    def test_aggregate_min(self):
        """Get min person value per household."""
        person_values = [50000, 30000, 40000]
        person_to_hh = [0, 0, 1]
        n_households = 2

        result = aggregate_min(person_values, person_to_hh, n_households)
        assert list(result) == [30000, 40000]

    def test_aggregate_count(self):
        """Count people per household."""
        person_to_hh = [0, 0, 1, 1, 1]
        n_households = 2

        result = aggregate_count(person_to_hh, n_households)
        assert list(result) == [2, 3]


class TestBroadcasting:
    """Test broadcasting from household to person level."""

    def test_broadcast_to_members(self):
        """Broadcast household value to all members."""
        household_values = [1000, 1500]  # 2 households
        person_to_hh = [0, 0, 1]  # 2 people in hh0, 1 in hh1

        result = broadcast_to_members(household_values, person_to_hh)
        assert list(result) == [1000, 1000, 1500]

    def test_broadcast_single_household(self):
        """Broadcast single household to all members."""
        household_values = [2000]
        person_to_hh = [0, 0, 0]

        result = broadcast_to_members(household_values, person_to_hh)
        assert list(result) == [2000, 2000, 2000]


class TestEntityIndex:
    """Test getting entity membership indices."""

    def test_get_household_index_for_person(self):
        """Get which household each person belongs to."""
        model = EntityModel(
            people={"p1": {}, "p2": {}, "p3": {}},
            households={
                "hh1": {"members": ["p1"]},
                "hh2": {"members": ["p2", "p3"]},
            },
        )

        indices = get_entity_index(model, "person", "household")
        assert list(indices) == [0, 1, 1]


class TestComplexCalculations:
    """Test complex multi-entity calculations."""

    def test_household_income_per_person(self):
        """Calculate household income divided by number of people."""
        model = EntityModel(
            people={
                "adult1": {"employment_income": 50000},
                "adult2": {"employment_income": 30000},
                "child1": {"employment_income": 0},
            },
            households={
                "hh": {"members": ["adult1", "adult2", "child1"]},
            },
        )

        # Get person incomes
        incomes = model.get_person_variable("employment_income", default=0)

        # Aggregate to household
        person_to_hh = model.person_to_household_index()
        n_hh = model.n_households

        hh_income = aggregate_sum(incomes, person_to_hh, n_hh)
        assert list(hh_income) == [80000]

        # Get household size
        hh_size = aggregate_count(person_to_hh, n_hh)
        assert list(hh_size) == [3]

        # Broadcast back to person and divide
        income_per_person = broadcast_to_members(hh_income, person_to_hh)
        size_per_person = broadcast_to_members(hh_size, person_to_hh)

        result = [i / s for i, s in zip(income_per_person, size_per_person)]
        assert result == [80000 / 3, 80000 / 3, 80000 / 3]

    def test_is_highest_earner_in_household(self):
        """Determine if each person is the highest earner."""
        model = EntityModel(
            people={
                "adult1": {"employment_income": 50000},
                "adult2": {"employment_income": 30000},
            },
            households={
                "hh": {"members": ["adult1", "adult2"]},
            },
        )

        incomes = model.get_person_variable("employment_income", default=0)
        person_to_hh = model.person_to_household_index()
        n_hh = model.n_households

        # Get max income in each household
        max_income = aggregate_max(incomes, person_to_hh, n_hh)

        # Broadcast back to person level
        max_per_person = broadcast_to_members(max_income, person_to_hh)

        # Compare
        is_highest = [i == m for i, m in zip(incomes, max_per_person)]
        assert is_highest == [True, False]

    def test_multi_household_benefit_calculation(self):
        """Calculate a benefit across multiple households."""
        model = EntityModel(
            people={
                "p1": {"employment_income": 20000, "is_adult": True},
                "p2": {"employment_income": 0, "is_adult": False},
                "p3": {"employment_income": 60000, "is_adult": True},
            },
            households={
                "hh1": {
                    "members": ["p1", "p2"]
                },  # Low income household with child
                "hh2": {"members": ["p3"]},  # High income single adult
            },
        )

        # Simplified benefit: £5000 if household income < £30000
        incomes = model.get_person_variable("employment_income", default=0)
        person_to_hh = model.person_to_household_index()
        n_hh = model.n_households

        hh_income = aggregate_sum(incomes, person_to_hh, n_hh)

        # Calculate benefit at household level
        benefit = [5000 if inc < 30000 else 0 for inc in hh_income]
        assert benefit == [5000, 0]
