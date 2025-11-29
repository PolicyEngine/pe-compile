"""AST-based formula parsing for robust extraction of dependencies.

Uses Python's ast module instead of regex for reliable parsing of
PolicyEngine formula patterns.
"""

import ast
from typing import Any


class VariableVisitor(ast.NodeVisitor):
    """Extract variable references from PE formula AST."""

    def __init__(self):
        self.variables: set[str] = set()
        self.entity_calls: list[tuple[str, str]] = []  # (entity, variable)

    def visit_Call(self, node: ast.Call) -> Any:
        """Visit function/method calls to find variable references."""
        # Pattern: person("variable_name", period)
        if isinstance(node.func, ast.Name):
            # Direct entity call: person("var", period)
            if node.func.id in ("person", "household", "benunit", "tax_unit"):
                if node.args and isinstance(node.args[0], ast.Constant):
                    var_name = node.args[0].value
                    if isinstance(var_name, str):
                        self.variables.add(var_name)
                        self.entity_calls.append((node.func.id, var_name))

            # add() function: add(person, period, ["var1", "var2"])
            elif node.func.id == "add":
                self._extract_add_variables(node)

        # Pattern: person.household("variable_name", period)
        # Also: household.members("variable_name", period)
        elif isinstance(node.func, ast.Attribute):
            # Entity hierarchy and members: person.household("var", period)
            if node.func.attr in (
                "household",
                "benunit",
                "tax_unit",
                "person",
                "members",
            ):
                if node.args and isinstance(node.args[0], ast.Constant):
                    var_name = node.args[0].value
                    if isinstance(var_name, str):
                        self.variables.add(var_name)
                        self.entity_calls.append((node.func.attr, var_name))

        # Continue visiting child nodes
        self.generic_visit(node)
        return None

    def _extract_add_variables(self, node: ast.Call) -> None:
        """Extract variables from add(entity, period, [vars]) call."""
        # Third argument should be the list of variable names
        if len(node.args) >= 3:
            var_list = node.args[2]
            if isinstance(var_list, ast.List):
                for elt in var_list.elts:
                    if isinstance(elt, ast.Constant) and isinstance(
                        elt.value, str
                    ):
                        self.variables.add(elt.value)


class ParameterVisitor(ast.NodeVisitor):
    """Extract parameter references from PE formula AST."""

    def __init__(self):
        self.parameters: set[str] = set()
        self.param_aliases: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> Any:
        """Detect parameter aliases: p = parameters(period)."""
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                if node.value.func.id == "parameters":
                    # Found alias assignment
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.param_aliases.add(target.id)
        self.generic_visit(node)
        return None

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        """Extract parameter paths from attribute access chains."""
        path = self._extract_attribute_path(node)
        if path:
            # Check if this is a parameter access
            parts = path.split(".")
            if parts[0] == "parameters" or parts[0] in self.param_aliases:
                # Remove the parameters() or alias prefix
                param_path = ".".join(parts[1:])
                if param_path:
                    self.parameters.add(param_path)

        self.generic_visit(node)
        return None

    def _extract_attribute_path(self, node: ast.AST) -> str | None:
        """Recursively build attribute path string."""
        if isinstance(node, ast.Attribute):
            base = self._extract_attribute_path(node.value)
            if base:
                return f"{base}.{node.attr}"
            return node.attr
        elif isinstance(node, ast.Call):
            # Handle parameters(period).path
            if isinstance(node.func, ast.Name):
                return node.func.id
        elif isinstance(node, ast.Name):
            return node.id
        return None


class WhereVisitor(ast.NodeVisitor):
    """Extract where() conditions from formulas."""

    def __init__(self):
        self.where_calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> Any:
        """Find where() function calls."""
        if isinstance(node.func, ast.Name) and node.func.id == "where":
            self.where_calls.append(node)
        self.generic_visit(node)
        return None


class FormulaAnalyzer:
    """Complete analyzer for PolicyEngine formula source code."""

    def __init__(self, source: str):
        self.source = source
        self.tree = ast.parse(source)

        # Extract all references
        self._analyze()

    def _analyze(self) -> None:
        """Run all visitors to extract dependencies."""
        # Extract variables
        var_visitor = VariableVisitor()
        var_visitor.visit(self.tree)
        self.variables = var_visitor.variables
        self.entity_calls = var_visitor.entity_calls

        # Extract parameters (two-pass for aliases)
        param_visitor = ParameterVisitor()
        param_visitor.visit(self.tree)
        self.parameters = param_visitor.parameters

        # Extract where conditions
        where_visitor = WhereVisitor()
        where_visitor.visit(self.tree)
        self.where_calls = where_visitor.where_calls

        # Detect entity type
        self.entity_type = self._detect_entity_type()

    def _detect_entity_type(self) -> str:
        """Detect the primary entity type from formula signature."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "formula":
                if node.args.args:
                    first_arg = node.args.args[0]
                    return first_arg.arg
        return "person"  # default


def extract_variable_references(source: str) -> set[str]:
    """Extract all variable references from formula source.

    Args:
        source: Python source code of the formula

    Returns:
        Set of variable names referenced in the formula
    """
    analyzer = FormulaAnalyzer(source)
    return analyzer.variables


def extract_parameter_references(source: str) -> set[str]:
    """Extract all parameter references from formula source.

    Args:
        source: Python source code of the formula

    Returns:
        Set of parameter paths referenced (e.g., "gov.tax.rate")
    """
    analyzer = FormulaAnalyzer(source)
    return analyzer.parameters


def extract_add_variables(source: str) -> list[str]:
    """Extract variable names from add() function calls.

    Args:
        source: Python source code of the formula

    Returns:
        List of variable names passed to add() functions
    """
    tree = ast.parse(source)
    variables: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "add":
                if len(node.args) >= 3:
                    var_list = node.args[2]
                    if isinstance(var_list, ast.List):
                        for elt in var_list.elts:
                            if isinstance(elt, ast.Constant):
                                if isinstance(elt.value, str):
                                    variables.append(elt.value)

        # Also check for list literals that might be variable lists
        if isinstance(node, ast.List):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(
                    elt.value, str
                ):
                    # Heuristic: if it looks like a variable name, include it
                    if "_" in elt.value or elt.value.islower():
                        if elt.value not in variables:
                            variables.append(elt.value)

    return variables


def extract_where_conditions(source: str) -> list[ast.Call]:
    """Extract where() condition AST nodes from formula.

    Args:
        source: Python source code of the formula

    Returns:
        List of AST Call nodes representing where() calls
    """
    analyzer = FormulaAnalyzer(source)
    return analyzer.where_calls
