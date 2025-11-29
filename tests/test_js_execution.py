"""Tests that execute generated JavaScript to verify correctness.

These tests actually run the generated JS code in Node.js to verify
the entity model, aggregation, and broadcasting work correctly.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from pe_compile.js_generator import JSCodeGenerator


def run_js(code: str, test_code: str) -> str:
    """Run JavaScript code and return the output."""
    full_code = code + "\n" + test_code
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False
    ) as f:
        f.write(full_code)
        f.flush()
        try:
            result = subprocess.run(
                ["node", f.name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError(f"JS error: {result.stderr}")
            return result.stdout.strip()
        finally:
            Path(f.name).unlink()


class TestJSRuntimeExecution:
    """Test the JS runtime by actually executing it."""

    def test_create_entity_model_single_person(self):
        """Entity model correctly handles single person."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_person_variable("income", is_input=True, default=0)

        code = gen.generate()
        # Remove export statements for Node execution
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: { "adult": { income: 50000 } },
    households: { "hh": { members: ["adult"] } }
};
const result = calculate(situation);
console.log(JSON.stringify({
    nPeople: result.model.nPeople,
    nHouseholds: result.model.nHouseholds,
    income: result.person.income
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        assert data["nPeople"] == 1
        assert data["nHouseholds"] == 1
        assert data["income"] == [50000]

    def test_create_entity_model_multi_person(self):
        """Entity model correctly handles multiple people."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_person_variable("income", is_input=True, default=0)
        gen.add_person_variable("age", is_input=True, default=30)

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: {
        "adult1": { income: 50000, age: 35 },
        "adult2": { income: 30000, age: 32 },
        "child": { income: 0, age: 10 }
    },
    households: { "hh": { members: ["adult1", "adult2", "child"] } }
};
const result = calculate(situation);
console.log(JSON.stringify({
    nPeople: result.model.nPeople,
    income: result.person.income,
    age: result.person.age
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        assert data["nPeople"] == 3
        assert data["income"] == [50000, 30000, 0]
        assert data["age"] == [35, 32, 10]


class TestAggregationExecution:
    """Test aggregation by executing generated JS."""

    def test_aggregate_sum_single_household(self):
        """Sum person incomes to household level."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_person_variable("income", is_input=True, default=0)
        gen.add_household_variable(
            "household_income",
            formula="aggregateSum(income, personToHH, nHouseholds)",
        )

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: {
        "adult1": { income: 50000 },
        "adult2": { income: 30000 },
        "child": { income: 0 }
    },
    households: { "hh": { members: ["adult1", "adult2", "child"] } }
};
const result = calculate(situation);
console.log(JSON.stringify({
    household_income: result.household.household_income
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        assert data["household_income"] == [80000]

    def test_aggregate_sum_multiple_households(self):
        """Sum across multiple households."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_person_variable("income", is_input=True, default=0)
        gen.add_household_variable(
            "household_income",
            formula="aggregateSum(income, personToHH, nHouseholds)",
        )

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: {
        "p1": { income: 50000 },
        "p2": { income: 30000 },
        "p3": { income: 40000 }
    },
    households: {
        "hh1": { members: ["p1", "p2"] },
        "hh2": { members: ["p3"] }
    }
};
const result = calculate(situation);
console.log(JSON.stringify({
    household_income: result.household.household_income
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        assert data["household_income"] == [80000, 40000]

    def test_aggregate_count(self):
        """Count people per household."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_person_variable("income", is_input=True, default=0)
        gen.add_household_variable(
            "household_size",
            formula="aggregateCount(personToHH, nHouseholds)",
        )

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: {
        "p1": { income: 0 },
        "p2": { income: 0 },
        "p3": { income: 0 }
    },
    households: {
        "hh1": { members: ["p1", "p2"] },
        "hh2": { members: ["p3"] }
    }
};
const result = calculate(situation);
console.log(JSON.stringify({
    household_size: result.household.household_size
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        assert data["household_size"] == [2, 1]


class TestBroadcastingExecution:
    """Test broadcasting by executing generated JS."""

    def test_broadcast_household_to_person(self):
        """Broadcast household value to all members."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_household_variable("rent", is_input=True, default=0)
        gen.add_person_variable(
            "rent_share",
            formula="broadcastToMembers(rent, personToHH)",
        )

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: {
        "p1": {},
        "p2": {},
        "p3": {}
    },
    households: {
        "hh1": { members: ["p1", "p2"], rent: 1000 },
        "hh2": { members: ["p3"], rent: 1500 }
    }
};
const result = calculate(situation);
console.log(JSON.stringify({
    rent_share: result.person.rent_share
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        # p1, p2 in hh1 (rent=1000), p3 in hh2 (rent=1500)
        assert data["rent_share"] == [1000, 1000, 1500]


class TestComplexCalculationsExecution:
    """Test complex multi-step calculations."""

    def test_means_tested_benefit(self):
        """Calculate a means-tested benefit."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        # Person inputs
        gen.add_person_variable("income", is_input=True, default=0)

        # Aggregate to household
        gen.add_household_variable(
            "household_income",
            formula="aggregateSum(income, personToHH, nHouseholds)",
        )

        # Means-tested benefit: £5000 if income < £30000
        gen.add_household_variable(
            "benefit",
            formula=(
                "arrayOps.where("
                "arrayOps.lt(household_income, 30000), "
                "household_income.map(() => 5000), "
                "household_income.map(() => 0)"
                ")"
            ),
        )

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: {
        "p1": { income: 20000 },
        "p2": { income: 0 },
        "p3": { income: 60000 }
    },
    households: {
        "hh1": { members: ["p1", "p2"] },
        "hh2": { members: ["p3"] }
    }
};
const result = calculate(situation);
console.log(JSON.stringify({
    household_income: result.household.household_income,
    benefit: result.household.benefit
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        # hh1 income = 20000 (< 30000) -> benefit 5000
        # hh2 income = 60000 (>= 30000) -> benefit 0
        assert data["household_income"] == [20000, 60000]
        assert data["benefit"] == [5000, 0]

    def test_income_tax_calculation(self):
        """Calculate income tax at person level."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_person_variable("income", is_input=True, default=0)
        gen.add_person_variable(
            "tax",
            formula="arrayOps.mul(income, 0.2)",  # 20% flat tax
        )
        gen.add_household_variable(
            "household_tax",
            formula="aggregateSum(tax, personToHH, nHouseholds)",
        )

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: {
        "adult1": { income: 50000 },
        "adult2": { income: 30000 },
        "child": { income: 0 }
    },
    households: { "hh": { members: ["adult1", "adult2", "child"] } }
};
const result = calculate(situation);
console.log(JSON.stringify({
    tax: result.person.tax,
    household_tax: result.household.household_tax
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        assert data["tax"] == [10000, 6000, 0]  # 20% of each income
        assert data["household_tax"] == [16000]  # Sum of all taxes

    def test_per_person_share_of_household_benefit(self):
        """Divide household benefit equally among members."""
        gen = JSCodeGenerator(
            include_entity_runtime=True,
            situation_based=True,
            module_type="none",
        )
        gen.add_household_variable("benefit", is_input=True, default=0)
        gen.add_household_variable(
            "household_size",
            formula="aggregateCount(personToHH, nHouseholds)",
        )
        gen.add_person_variable(
            "benefit_share",
            formula=(
                "arrayOps.div("
                "broadcastToMembers(benefit, personToHH), "
                "broadcastToMembers(household_size, personToHH)"
                ")"
            ),
        )

        code = gen.generate()
        code = code.replace("export { calculate, createEntityModel };", "")
        code = code.replace("export default calculate;", "")

        test = """
const situation = {
    people: { "p1": {}, "p2": {}, "p3": {} },
    households: {
        "hh1": { members: ["p1", "p2"], benefit: 1000 },
        "hh2": { members: ["p3"], benefit: 600 }
    }
};
const result = calculate(situation);
console.log(JSON.stringify({
    benefit_share: result.person.benefit_share
}));
"""
        output = run_js(code, test)
        data = json.loads(output)
        # hh1: 1000 / 2 = 500 each, hh2: 600 / 1 = 600
        assert data["benefit_share"] == [500, 500, 600]
