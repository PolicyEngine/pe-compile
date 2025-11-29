"""Tests for standalone Python code generation."""

from pe_compile.generator import (
    CodeGenerator,
    generate_standalone_function,
    inline_parameters,
)


class TestGenerateStandaloneFunction:
    """Test generating standalone calculation functions."""

    def test_simple_addition(self):
        """Generate a simple addition function."""
        formula_source = """
def formula(person, period):
    a = person("variable_a", period)
    b = person("variable_b", period)
    return a + b
"""
        result = generate_standalone_function(
            name="my_sum",
            formula_source=formula_source,
            input_variables=["variable_a", "variable_b"],
        )

        # Should generate a standalone function
        assert "def my_sum(" in result
        assert "variable_a" in result
        assert "variable_b" in result
        # Should not reference person or period
        assert "person(" not in result

    def test_parameter_inlining(self):
        """Inline parameter values into the function."""
        formula_source = """
def formula(person, period, parameters):
    rate = parameters(period).gov.tax.rate
    return person("income", period) * rate
"""
        parameter_values = {"gov.tax.rate": 0.20}

        result = generate_standalone_function(
            name="calculate_tax",
            formula_source=formula_source,
            input_variables=["income"],
            parameter_values=parameter_values,
        )

        assert "def calculate_tax(" in result
        assert "0.20" in result or "0.2" in result
        assert "parameters(" not in result

    def test_numpy_functions_preserved(self):
        """Preserve numpy function calls."""
        formula_source = """
def formula(person, period):
    income = person("income", period)
    return np.maximum(income - 12570, 0)
"""
        result = generate_standalone_function(
            name="taxable_income",
            formula_source=formula_source,
            input_variables=["income"],
        )

        assert "np.maximum" in result or "numpy.maximum" in result

    def test_where_clause_translation(self):
        """Translate where clauses properly."""
        formula_source = """
def formula(person, period):
    is_eligible = person("is_eligible", period)
    amount = person("benefit_amount", period)
    return where(is_eligible, amount, 0)
"""
        result = generate_standalone_function(
            name="actual_benefit",
            formula_source=formula_source,
            input_variables=["is_eligible", "benefit_amount"],
        )

        assert "def actual_benefit(" in result
        # Should use numpy where
        assert "where" in result


class TestInlineParameters:
    """Test parameter value inlining."""

    def test_simple_parameter(self):
        """Inline a simple parameter value."""
        code = "rate = parameters(period).gov.tax.rate"
        values = {"gov.tax.rate": 0.20}

        result = inline_parameters(code, values)
        assert "0.2" in result
        assert "parameters(" not in result

    def test_nested_parameter(self):
        """Inline a nested parameter path."""
        code = "amount = parameters(period).gov.dwp.uc.standard.single"
        values = {"gov.dwp.uc.standard.single": 334.91}

        result = inline_parameters(code, values)
        assert "334.91" in result

    def test_multiple_parameters(self):
        """Inline multiple parameter values."""
        code = """
rate = parameters(period).gov.tax.rate
threshold = parameters(period).gov.tax.threshold
"""
        values = {
            "gov.tax.rate": 0.20,
            "gov.tax.threshold": 12570,
        }

        result = inline_parameters(code, values)
        assert "0.2" in result
        assert "12570" in result

    def test_parameter_with_p_alias(self):
        """Handle p = parameters(period) alias pattern."""
        code = """
p = parameters(period)
rate = p.gov.tax.rate
threshold = p.gov.tax.threshold
"""
        values = {
            "gov.tax.rate": 0.20,
            "gov.tax.threshold": 12570,
        }

        result = inline_parameters(code, values)
        assert "0.2" in result
        assert "12570" in result


class TestCodeGenerator:
    """Test the full code generator."""

    def test_generate_module(self):
        """Generate a complete standalone module."""
        generator = CodeGenerator()

        generator.add_variable(
            name="gross_income",
            formula_source="""
def formula(person, period):
    emp = person("employment_income", period)
    self_emp = person("self_employment_income", period)
    return emp + self_emp
""",
            dependencies=["employment_income", "self_employment_income"],
            is_input=False,
        )

        generator.add_input_variable(
            name="employment_income",
            default_value=0,
            value_type=float,
        )

        generator.add_input_variable(
            name="self_employment_income",
            default_value=0,
            value_type=float,
        )

        module_code = generator.generate_module()

        # Should have imports
        assert "import numpy as np" in module_code
        # Should have input variables as function parameters
        assert "employment_income" in module_code
        assert "self_employment_income" in module_code
        # Should have the calculation
        assert "gross_income" in module_code

    def test_generate_with_parameters(self):
        """Generate module with inlined parameters."""
        generator = CodeGenerator()

        generator.add_variable(
            name="income_tax",
            formula_source="""
def formula(person, period, parameters):
    income = person("taxable_income", period)
    rate = parameters(period).gov.tax.basic_rate
    return income * rate
""",
            dependencies=["taxable_income"],
            is_input=False,
        )

        generator.add_input_variable(
            name="taxable_income",
            default_value=0,
            value_type=float,
        )

        generator.add_parameter(
            path="gov.tax.basic_rate",
            value=0.20,
        )

        module_code = generator.generate_module()

        assert "0.2" in module_code
        assert "parameters(" not in module_code

    def test_generate_callable_module(self):
        """Generated module should be executable."""
        generator = CodeGenerator()

        generator.add_input_variable(
            "income", default_value=0, value_type=float
        )
        generator.add_variable(
            name="doubled_income",
            formula_source="""
def formula(person, period):
    return person("income", period) * 2
""",
            dependencies=["income"],
            is_input=False,
        )

        module_code = generator.generate_module()

        # Execute the generated code
        namespace = {}
        exec(module_code, namespace)

        # Should have a calculate function
        assert "calculate" in namespace
        result = namespace["calculate"](income=50000)
        assert result["doubled_income"] == 100000

    def test_topological_order(self):
        """Variables calculated in dependency order."""
        generator = CodeGenerator()

        # Add in wrong order
        generator.add_variable(
            name="c",
            formula_source="def formula(p, t): return p('b', t) + 1",
            dependencies=["b"],
            is_input=False,
        )
        generator.add_variable(
            name="b",
            formula_source="def formula(p, t): return p('a', t) * 2",
            dependencies=["a"],
            is_input=False,
        )
        generator.add_input_variable("a", default_value=0, value_type=float)

        module_code = generator.generate_module()

        # Verify the order by executing and checking results
        namespace = {}
        exec(module_code, namespace)
        result = namespace["calculate"](a=5)
        assert result["b"] == 10  # 5 * 2
        assert result["c"] == 11  # 10 + 1
