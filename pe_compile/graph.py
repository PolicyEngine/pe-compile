"""
Dependency graph extraction from PolicyEngine variables.

This module provides tools to:
1. Parse PolicyEngine variable formulas to extract dependencies
2. Build a complete dependency graph of variables and parameters
3. Perform topological sorting for correct calculation order
"""

import inspect
import re
from dataclasses import dataclass, field
from typing import Optional

from pe_compile.ast_parser import FormulaAnalyzer


@dataclass
class Dependencies:
    """Dependencies extracted from a formula."""

    variables: set[str] = field(default_factory=set)
    parameters: set[str] = field(default_factory=set)


@dataclass
class VariableInfo:
    """Information about a PolicyEngine variable."""

    name: str
    formula_source: str
    dependencies: set[str] = field(default_factory=set)
    parameter_dependencies: set[str] = field(default_factory=set)
    entity: str = "person"
    definition_period: str = "year"
    value_type: type = float
    default_value: float = 0
    is_input: bool = False


class DependencyGraph:
    """Graph of variable dependencies for a PolicyEngine system."""

    def __init__(self):
        self.variables: dict[str, VariableInfo] = {}
        self.parameters: dict[str, float] = {}

    def add_variable(
        self,
        name: str,
        dependencies: list[str],
        formula_source: str,
        entity: str = "person",
        definition_period: str = "year",
        value_type: type = float,
        default_value: float = 0,
        is_input: bool = False,
        parameter_dependencies: Optional[list[str]] = None,
    ) -> None:
        """Add a variable to the graph."""
        self.variables[name] = VariableInfo(
            name=name,
            formula_source=formula_source,
            dependencies=set(dependencies),
            parameter_dependencies=set(parameter_dependencies or []),
            entity=entity,
            definition_period=definition_period,
            value_type=value_type,
            default_value=default_value,
            is_input=is_input,
        )

    def add_parameter(self, path: str, value: float) -> None:
        """Add a parameter value to the graph."""
        self.parameters[path] = value

    def get_transitive_dependencies(self, variable_name: str) -> set[str]:
        """Get all transitive dependencies of a variable."""
        visited = set()
        to_visit = [variable_name]

        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            if current == variable_name:
                # Don't add the starting variable itself
                pass
            else:
                visited.add(current)

            if current in self.variables:
                for dep in self.variables[current].dependencies:
                    if dep not in visited:
                        to_visit.append(dep)

        return visited

    def topological_sort(self, target_variables: list[str]) -> list[str]:
        """
        Sort variables in dependency order (dependencies first).

        Returns a list where each variable appears after all its dependencies.
        """
        # First, collect all variables we need
        all_vars = set(target_variables)
        for var in target_variables:
            all_vars.update(self.get_transitive_dependencies(var))

        # Kahn's algorithm for topological sort
        # Build in-degree map (how many dependencies each var has)
        in_degree = {var: 0 for var in all_vars}
        for var in all_vars:
            if var in self.variables:
                for dep in self.variables[var].dependencies:
                    if dep in all_vars:
                        in_degree[var] += 1

        # Start with variables that have no dependencies
        queue = [var for var, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            # Reduce in-degree for variables that depend on current
            for var in all_vars:
                if var in self.variables:
                    if current in self.variables[var].dependencies:
                        in_degree[var] -= 1
                        if in_degree[var] == 0:
                            queue.append(var)

        # Handle cycles - just add remaining variables
        for var in all_vars:
            if var not in result:
                result.append(var)

        return result


def extract_dependencies_from_formula(formula_source: str) -> Dependencies:
    """
    Extract variable and parameter dependencies from a formula's source code.

    Uses AST parsing for robust extraction, with regex fallback for edge cases.

    Parses the formula to find:
    - Variable references: person("variable_name", period)
    - Parameter references: parameters(period).gov.path.to.param
    """
    deps = Dependencies()

    if not formula_source.strip():
        return deps

    # Try AST-based parsing first (more robust)
    try:
        analyzer = FormulaAnalyzer(formula_source)
        deps.variables = analyzer.variables
        deps.parameters = analyzer.parameters
        return deps
    except SyntaxError:
        # Fall back to regex for malformed source
        pass

    # Fallback: regex-based parsing
    # Pattern for variable references: entity("variable_name", period)
    var_pattern = (
        r"(?:person|household|tax_unit|family|benunit|state)"
        r'\s*\(\s*["\'](\w+)["\']'
    )
    for match in re.finditer(var_pattern, formula_source):
        deps.variables.add(match.group(1))

    # Also match .members("variable_name", period) pattern
    members_pattern = r'\.members\s*\(\s*["\'](\w+)["\']'
    for match in re.finditer(members_pattern, formula_source):
        deps.variables.add(match.group(1))

    # Pattern for parameter references
    alias_pattern = r"(\w+)\s*=\s*parameters\s*\(\s*period\s*\)"
    aliases = ["parameters(period)"]
    for match in re.finditer(alias_pattern, formula_source):
        aliases.append(match.group(1))

    for alias in aliases:
        escaped_alias = re.escape(alias)
        param_pattern = rf"{escaped_alias}((?:\.\w+)+)"
        for match in re.finditer(param_pattern, formula_source):
            param_path = match.group(1).lstrip(".")
            if param_path:
                deps.parameters.add(param_path)

    return deps


def build_dependency_graph(
    variables: dict[str, type],
    parameters: Optional[dict[str, float]] = None,
) -> DependencyGraph:
    """
    Build a dependency graph from PolicyEngine variable classes.

    Args:
        variables: Dict mapping variable names to variable classes
        parameters: Optional dict mapping parameter paths to values

    Returns:
        A DependencyGraph containing all variable information
    """
    graph = DependencyGraph()

    for name, var_class in variables.items():
        # Get formula source if it exists
        formula_source = ""
        if hasattr(var_class, "formula"):
            try:
                formula_source = inspect.getsource(var_class.formula)
            except (TypeError, OSError):
                # Can't get source for built-in or C functions
                formula_source = ""

        # Extract dependencies from formula
        deps = extract_dependencies_from_formula(formula_source)

        # Get entity info
        entity = "person"
        if hasattr(var_class, "entity"):
            entity = getattr(var_class.entity, "key", "person")

        # Get other metadata
        definition_period = getattr(var_class, "definition_period", "year")
        value_type = getattr(var_class, "value_type", float)
        default_value = getattr(var_class, "default_value", 0)

        # A variable is an input if it has no formula
        is_input = not formula_source.strip()

        graph.add_variable(
            name=name,
            dependencies=list(deps.variables),
            formula_source=formula_source,
            entity=entity,
            definition_period=definition_period,
            value_type=value_type,
            default_value=default_value,
            is_input=is_input,
            parameter_dependencies=list(deps.parameters),
        )

    # Add parameters if provided
    if parameters:
        for path, value in parameters.items():
            graph.add_parameter(path, value)

    return graph
