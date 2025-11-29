"""
Standalone Python code generation from PolicyEngine variables.

This module generates executable Python code that performs the same
calculations as PolicyEngine variables, but without the framework overhead.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from pe_compile.graph import DependencyGraph


def inline_parameters(code: str, parameter_values: dict[str, float]) -> str:
    """
    Replace parameter references with their actual values.

    Handles both direct parameter access and alias patterns:
    - parameters(period).gov.tax.rate -> 0.20
    - p = parameters(period); p.gov.tax.rate -> 0.20
    """
    result = code

    # Find any parameter aliases (p = parameters(period))
    alias_pattern = r"(\w+)\s*=\s*parameters\s*\(\s*period\s*\)"
    aliases = []
    for match in re.finditer(alias_pattern, result):
        aliases.append(match.group(1))

    # Remove alias assignments (but only standalone ones, not inline)
    result = re.sub(
        r"^\s*\w+\s*=\s*parameters\s*\(\s*period\s*\)\s*$\n?",
        "",
        result,
        flags=re.MULTILINE,
    )

    # Replace parameter accesses with values - need to do longest paths first
    # to avoid partial replacements
    sorted_params = sorted(
        parameter_values.items(), key=lambda x: len(x[0]), reverse=True
    )

    for path, value in sorted_params:
        # Direct access: parameters(period).path.to.param
        direct_pattern = rf"parameters\s*\(\s*period\s*\)\.{re.escape(path)}"
        result = re.sub(direct_pattern, str(value), result)

        # Alias access: p.path.to.param (where p is an alias)
        for alias in aliases:
            alias_access_pattern = (
                rf"\b{re.escape(alias)}\.{re.escape(path)}\b"
            )
            result = re.sub(alias_access_pattern, str(value), result)

    return result


def generate_standalone_function(
    name: str,
    formula_source: str,
    input_variables: list[str],
    parameter_values: Optional[dict[str, float]] = None,
) -> str:
    """
    Generate a standalone function from a PolicyEngine formula.

    Transforms:
        def formula(person, period):
            return person("income", period) * 0.2

    Into:
        def calculate_tax(income):
            return income * 0.2
    """
    # Start with the formula body
    result = formula_source

    # Inline parameters if provided
    if parameter_values:
        result = inline_parameters(result, parameter_values)

    # Remove the function definition line and extract body
    lines = result.strip().split("\n")
    body_lines = []
    in_body = False
    indent_to_remove = 0

    for line in lines:
        if line.strip().startswith("def formula"):
            in_body = True
            continue
        if in_body:
            if not indent_to_remove and line.strip():
                # Detect indentation of first body line
                indent_to_remove = len(line) - len(line.lstrip())
            if line.strip():
                # Remove the detected indentation
                if len(line) >= indent_to_remove:
                    body_lines.append(line[indent_to_remove:])
                else:
                    body_lines.append(line.lstrip())
            else:
                body_lines.append("")

    body = "\n".join(body_lines)

    # Replace entity variable access with direct variable names
    # person("variable_name", period) -> variable_name
    entity_pattern = (
        r"(?:person|household|tax_unit|family|benunit|state)"
        r'\s*\(\s*["\'](\w+)["\']\s*,\s*period\s*\)'
    )
    body = re.sub(entity_pattern, r"\1", body)

    # Also handle .members() pattern
    # household.members("var", period) -> var
    members_pattern = r'\w+\.members\s*\(\s*["\'](\w+)["\']\s*,\s*period\s*\)'
    body = re.sub(members_pattern, r"\1", body)

    # Handle .sum() aggregation
    # household.sum(expression) -> np.sum(expression)
    body = re.sub(r"\w+\.sum\s*\(", "np.sum(", body)

    # Generate function signature
    params = ", ".join(input_variables)
    function_code = f"def {name}({params}):\n"

    # Indent body
    for line in body.split("\n"):
        if line.strip():
            function_code += f"    {line}\n"
        else:
            function_code += "\n"

    return function_code


@dataclass
class InputVariable:
    """An input variable for the generated calculator."""

    name: str
    default_value: Any = 0
    value_type: type = float


@dataclass
class ComputedVariable:
    """A computed variable for the generated calculator."""

    name: str
    formula_source: str
    dependencies: list[str] = field(default_factory=list)


class CodeGenerator:
    """
    Generator for standalone PolicyEngine calculators.

    Usage:
        generator = CodeGenerator()
        generator.add_input_variable("income", default_value=0)
        generator.add_variable(
            "tax", formula_source="...", dependencies=["income"]
        )
        generator.add_parameter("gov.tax.rate", 0.20)
        code = generator.generate_module()
    """

    def __init__(self):
        self.input_variables: dict[str, InputVariable] = {}
        self.computed_variables: dict[str, ComputedVariable] = {}
        self.parameters: dict[str, float] = {}
        self.graph = DependencyGraph()

    def add_input_variable(
        self,
        name: str,
        default_value: Any = 0,
        value_type: type = float,
    ) -> None:
        """Add an input variable."""
        self.input_variables[name] = InputVariable(
            name=name,
            default_value=default_value,
            value_type=value_type,
        )
        self.graph.add_variable(
            name=name,
            dependencies=[],
            formula_source="",
            is_input=True,
            default_value=default_value,
            value_type=value_type,
        )

    def add_variable(
        self,
        name: str,
        formula_source: str,
        dependencies: list[str],
        is_input: bool = False,
    ) -> None:
        """Add a computed variable."""
        if is_input:
            self.add_input_variable(name)
            return

        self.computed_variables[name] = ComputedVariable(
            name=name,
            formula_source=formula_source,
            dependencies=dependencies,
        )
        self.graph.add_variable(
            name=name,
            dependencies=dependencies,
            formula_source=formula_source,
            is_input=False,
        )

    def add_parameter(self, path: str, value: float) -> None:
        """Add a parameter value."""
        self.parameters[path] = value
        self.graph.add_parameter(path, value)

    def generate_module(self) -> str:
        """Generate a complete standalone Python module."""
        lines = [
            '"""',
            "Auto-generated standalone calculator.",
            "Generated by pe-compile from PolicyEngine variable definitions.",
            '"""',
            "",
            "import numpy as np",
            "from numpy import where, maximum, minimum, zeros, ones",
            "",
            "",
        ]

        # Get topological order
        all_vars = list(self.computed_variables.keys())
        sorted_vars = self.graph.topological_sort(all_vars)

        # Generate the main calculate function
        input_params = []
        for name, var in self.input_variables.items():
            default = var.default_value
            if isinstance(default, str):
                default = f'"{default}"'
            input_params.append(f"{name}={default}")

        lines.append(f"def calculate({', '.join(input_params)}):")
        lines.append('    """')
        lines.append("    Calculate all derived values from inputs.")
        lines.append("")
        lines.append("    Returns:")
        lines.append("        dict: All calculated values")
        lines.append('    """')
        lines.append("    results = {}")
        lines.append("")

        # Store inputs in results
        for name in self.input_variables:
            lines.append(f"    results['{name}'] = {name}")
        lines.append("")

        # Generate calculations in dependency order
        for var_name in sorted_vars:
            if var_name in self.input_variables:
                continue  # Skip inputs, already handled

            if var_name not in self.computed_variables:
                continue  # Skip if not a computed variable we know about

            var = self.computed_variables[var_name]
            lines.append(f"    # Calculate {var_name}")

            # Generate the calculation code
            calc_code = self._generate_calculation(var)
            for calc_line in calc_code.split("\n"):
                if calc_line.strip():
                    lines.append(f"    {calc_line}")

            lines.append(f"    results['{var_name}'] = {var_name}")
            lines.append("")

        lines.append("    return results")
        lines.append("")

        return "\n".join(lines)

    def _generate_calculation(self, var: ComputedVariable) -> str:
        """Generate calculation code for a single variable."""
        formula = var.formula_source

        # Inline parameters
        formula = inline_parameters(formula, self.parameters)

        # Extract just the formula body
        lines = formula.strip().split("\n")
        body_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("def formula"):
                # Check for single-line formula: def formula(...): return ...
                if ":" in stripped:
                    # Find the position after the first colon in the def line
                    colon_match = re.search(r"\):\s*(.+)$", stripped)
                    if colon_match:
                        # Single line formula
                        body_lines.append(colon_match.group(1))
                continue
            if stripped:
                body_lines.append(stripped)

        body = "\n".join(body_lines)

        # Replace entity references with variable names
        # Match both full names and short aliases (p, person, household, etc.)
        # Pattern: identifier("variable_name", period_arg)
        entity_pattern = r'\b\w+\s*\(\s*["\'](\w+)["\']\s*,\s*\w+\s*\)'
        body = re.sub(entity_pattern, r"results['\1']", body)

        # Handle .members() pattern
        members_pattern = r'\w+\.members\s*\(\s*["\'](\w+)["\']\s*,\s*\w+\s*\)'
        body = re.sub(members_pattern, r"results['\1']", body)

        # Handle .sum() aggregation
        body = re.sub(r"\w+\.sum\s*\(", "np.sum(", body)

        # Replace return statement with assignment
        if body.strip().startswith("return "):
            body = f"{var.name} = " + body.strip()[7:]

        return body
