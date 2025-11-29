"""Tests for JavaScript code generation."""

import pytest

from pe_compile.js_generator import (JSCodeGenerator, generate_js_function,
                                     python_to_js_expression)


class TestPythonToJsExpression:
    """Test converting Python expressions to JavaScript."""

    def test_simple_arithmetic(self):
        """Convert basic arithmetic."""
        assert python_to_js_expression("a + b") == "a + b"
        assert python_to_js_expression("a - b") == "a - b"
        assert python_to_js_expression("a * b") == "a * b"
        assert python_to_js_expression("a / b") == "a / b"

    def test_numpy_max(self):
        """Convert np.maximum to Math.max."""
        expr = "np.maximum(0, income - threshold)"
        result = python_to_js_expression(expr)
        assert "Math.max" in result
        assert "np.maximum" not in result

    def test_numpy_min(self):
        """Convert np.minimum to Math.min."""
        expr = "np.minimum(income, cap)"
        result = python_to_js_expression(expr)
        assert "Math.min" in result

    def test_max_function(self):
        """Convert max() to Math.max."""
        expr = "max(0, income - 12570)"
        result = python_to_js_expression(expr)
        assert "Math.max" in result

    def test_min_function(self):
        """Convert min() to Math.min."""
        expr = "min(income, 50000)"
        result = python_to_js_expression(expr)
        assert "Math.min" in result

    def test_where_to_ternary(self):
        """Convert where(cond, a, b) to ternary."""
        expr = "where(income > 50000, income * 0.4, income * 0.2)"
        result = python_to_js_expression(expr)
        # Should produce: (income > 50000) ? (income * 0.4) : (income * 0.2)
        assert "?" in result
        assert ":" in result

    def test_nested_where(self):
        """Convert nested where to nested ternary."""
        expr = "where(a > 100, 1, where(a > 50, 2, 3))"
        result = python_to_js_expression(expr)
        # Should have two ternary operators
        assert result.count("?") == 2
        assert result.count(":") == 2

    def test_numpy_where(self):
        """Convert np.where to ternary."""
        expr = "np.where(is_adult, income, 0)"
        result = python_to_js_expression(expr)
        assert "?" in result

    def test_boolean_true_false(self):
        """Convert Python True/False to JS true/false."""
        assert "true" in python_to_js_expression("True")
        assert "false" in python_to_js_expression("False")

    def test_floor_division(self):
        """Convert // to Math.floor division."""
        expr = "income // 1000"
        result = python_to_js_expression(expr)
        assert "Math.floor" in result

    def test_power_operator(self):
        """Convert ** to Math.pow or **."""
        expr = "base ** 2"
        result = python_to_js_expression(expr)
        # JS supports ** since ES2016, or could use Math.pow
        assert "**" in result or "Math.pow" in result

    def test_numpy_ceil(self):
        """Convert np.ceil to Math.ceil."""
        expr = "np.ceil(value)"
        result = python_to_js_expression(expr)
        assert "Math.ceil" in result

    def test_numpy_floor(self):
        """Convert np.floor to Math.floor."""
        expr = "np.floor(value)"
        result = python_to_js_expression(expr)
        assert "Math.floor" in result

    def test_numpy_abs(self):
        """Convert np.abs to Math.abs."""
        expr = "np.abs(value)"
        result = python_to_js_expression(expr)
        assert "Math.abs" in result


class TestGenerateJsFunction:
    """Test generating complete JS functions."""

    def test_simple_function(self):
        """Generate a simple JS function."""
        code = generate_js_function(
            name="calculateTax",
            inputs=["income"],
            body="return income * 0.2;",
        )
        assert "function calculateTax(income)" in code
        assert "return income * 0.2;" in code

    def test_function_with_defaults(self):
        """Generate function with default parameter values."""
        code = generate_js_function(
            name="calculate",
            inputs=["income", "rate"],
            defaults={"income": 0, "rate": 0.2},
            body="return income * rate;",
        )
        assert "income = 0" in code or "income=0" in code
        assert "rate = 0.2" in code or "rate=0.2" in code

    def test_arrow_function(self):
        """Generate ES6 arrow function."""
        code = generate_js_function(
            name="calculateTax",
            inputs=["income"],
            body="return income * 0.2;",
            arrow=True,
        )
        assert "=>" in code

    def test_typescript_types(self):
        """Generate TypeScript with types."""
        code = generate_js_function(
            name="calculateTax",
            inputs=["income"],
            body="return income * 0.2;",
            typescript=True,
            input_types={"income": "number"},
            return_type="number",
        )
        assert "income: number" in code
        assert ": number" in code  # Return type


class TestJSCodeGenerator:
    """Test the complete JS code generator."""

    def test_generate_module(self):
        """Generate a complete JS module."""
        gen = JSCodeGenerator()
        gen.add_input("income", default=0)
        gen.add_input("allowance", default=12570)
        gen.add_calculation(
            "taxable_income",
            "Math.max(0, income - allowance)",
        )
        gen.add_calculation(
            "income_tax",
            "taxable_income * 0.2",
        )

        code = gen.generate()

        assert "function calculate" in code
        assert "income" in code
        assert "allowance" in code
        assert "taxable_income" in code
        assert "income_tax" in code

    def test_generate_esm_module(self):
        """Generate ES module with export."""
        gen = JSCodeGenerator(module_type="esm")
        gen.add_input("income", default=0)
        gen.add_calculation("tax", "income * 0.2")

        code = gen.generate()

        assert "export" in code

    def test_generate_commonjs_module(self):
        """Generate CommonJS module."""
        gen = JSCodeGenerator(module_type="commonjs")
        gen.add_input("income", default=0)
        gen.add_calculation("tax", "income * 0.2")

        code = gen.generate()

        assert "module.exports" in code

    def test_generate_typescript(self):
        """Generate TypeScript module."""
        gen = JSCodeGenerator(typescript=True)
        gen.add_input("income", default=0, type_hint="number")
        gen.add_calculation("tax", "income * 0.2")

        code = gen.generate()

        assert ": number" in code
        # Should have .ts-compatible syntax

    def test_calculation_order(self):
        """Calculations should be in dependency order."""
        gen = JSCodeGenerator()
        gen.add_input("a", default=0)
        gen.add_calculation("b", "a * 2")
        gen.add_calculation("c", "b + 1")

        code = gen.generate()

        # b should appear before c in the code
        b_pos = (
            code.find("const b =") if "const b =" in code else code.find("b =")
        )
        c_pos = (
            code.find("const c =") if "const c =" in code else code.find("c =")
        )
        assert b_pos < c_pos

    def test_jsdoc_comments(self):
        """Include JSDoc comments."""
        gen = JSCodeGenerator(include_jsdoc=True)
        gen.add_input("income", default=0, description="Annual income")
        gen.add_calculation("tax", "income * 0.2")

        code = gen.generate()

        assert "/**" in code
        assert "@param" in code


class TestFromPythonFormula:
    """Test converting Python PE formulas to JS."""

    def test_simple_formula(self):
        """Convert a simple Python formula to JS."""
        python_formula = """
def formula(person, period):
    income = person("employment_income", period)
    return income * 0.2
"""
        gen = JSCodeGenerator()
        gen.add_from_python_formula(
            "income_tax",
            python_formula,
            inputs=["employment_income"],
        )

        code = gen.generate()

        assert "employment_income" in code
        assert "0.2" in code
        # Should not have Python-specific syntax
        assert "person(" not in code
        assert "period" not in code

    def test_formula_with_max(self):
        """Convert formula with max() to JS."""
        python_formula = """
def formula(person, period):
    income = person("employment_income", period)
    threshold = 12570
    return max(0, income - threshold)
"""
        gen = JSCodeGenerator()
        gen.add_from_python_formula(
            "taxable_income",
            python_formula,
            inputs=["employment_income"],
            parameters={"threshold": 12570},
        )

        code = gen.generate()

        assert "Math.max" in code
        assert "12570" in code

    def test_formula_with_where(self):
        """Convert formula with where() to ternary."""
        python_formula = """
def formula(person, period):
    income = person("income", period)
    return where(income > 50000, income * 0.4, income * 0.2)
"""
        gen = JSCodeGenerator()
        gen.add_from_python_formula(
            "tax",
            python_formula,
            inputs=["income"],
        )

        code = gen.generate()

        assert "?" in code
        assert ":" in code
        assert "50000" in code
