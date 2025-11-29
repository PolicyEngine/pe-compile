"""
Extract variables and parameters from PolicyEngine country systems.

This module handles:
1. Loading country tax-benefit systems
2. Extracting parameter values for specific years
3. Filtering to only required variables and their dependencies
4. Stripping unnecessary metadata (references, descriptions, etc.)
"""

import inspect
from dataclasses import dataclass
from typing import Any, Optional

from pe_compile.graph import (
    DependencyGraph,
    extract_dependencies_from_formula,
)


@dataclass
class ExtractedParameter:
    """A parameter extracted from PolicyEngine for a specific year."""

    path: str
    value: Any
    # Metadata we strip out for the compiled version
    description: Optional[str] = None
    reference: Optional[str] = None
    unit: Optional[str] = None


@dataclass
class ExtractedVariable:
    """A variable extracted from PolicyEngine."""

    name: str
    formula_source: str
    dependencies: set[str]
    parameter_dependencies: set[str]
    entity: str = "person"
    definition_period: str = "year"
    value_type: type = float
    default_value: Any = 0
    is_input: bool = False


def get_parameter_value_at_instant(
    parameter_node: Any,
    instant: str,
) -> Any:
    """
    Get the value of a parameter at a specific instant.

    Handles both scalar parameters and parameter scales (tax brackets, etc.)
    """
    try:
        # Try to get value at instant
        if hasattr(parameter_node, "__call__"):
            return parameter_node(instant)
        return parameter_node
    except Exception:
        return None


def extract_parameter_tree(
    params: Any,
    instant: str,
    prefix: str = "",
) -> dict[str, ExtractedParameter]:
    """
    Recursively extract all parameter values from a parameter tree.

    Returns a flat dictionary mapping paths to ExtractedParameter objects.
    """
    result = {}

    # Get children if this is a parameter node
    if hasattr(params, "_children"):
        children = params._children
    elif hasattr(params, "__iter__") and not isinstance(params, (str, bytes)):
        # It's iterable but not a string
        try:
            children = {str(i): v for i, v in enumerate(params)}
        except Exception:
            children = {}
    else:
        children = {}

    for name, child in children.items():
        path = f"{prefix}.{name}" if prefix else name

        # Check if this is a leaf parameter (has values)
        if hasattr(child, "values_list") or hasattr(child, "__call__"):
            try:
                value = get_parameter_value_at_instant(child, instant)
                if value is not None:
                    result[path] = ExtractedParameter(
                        path=path,
                        value=value,
                        description=getattr(child, "description", None),
                        reference=getattr(child, "reference", None),
                        unit=getattr(child, "unit", None),
                    )
            except Exception:
                pass

        # Recurse into children
        if hasattr(child, "_children"):
            result.update(extract_parameter_tree(child, instant, path))

    return result


def extract_variables_for_targets(
    system: Any,
    target_variables: list[str],
    year: int,
) -> tuple[dict[str, ExtractedVariable], dict[str, ExtractedParameter]]:
    """
    Extract all variables needed to compute target_variables.

    Returns:
        Tuple of (variables dict, parameters dict)
    """
    instant = f"{year}-01-01"

    # Collect all variables we need (targets + dependencies)
    all_var_names = set(target_variables)
    to_process = list(target_variables)
    processed = set()

    variables = {}
    all_param_paths = set()

    while to_process:
        var_name = to_process.pop()
        if var_name in processed:
            continue
        processed.add(var_name)

        # Get variable from system
        var_class = system.get_variable(var_name)
        if var_class is None:
            continue

        # Extract formula source
        formula_source = ""
        if hasattr(var_class, "formula"):
            try:
                formula_source = inspect.getsource(var_class.formula)
            except (TypeError, OSError):
                pass

        # Extract dependencies
        deps = extract_dependencies_from_formula(formula_source)

        # Get entity info
        entity = "person"
        if hasattr(var_class, "entity"):
            entity = getattr(var_class.entity, "key", "person")

        # Determine if input variable
        is_input = not formula_source.strip()

        variables[var_name] = ExtractedVariable(
            name=var_name,
            formula_source=formula_source,
            dependencies=deps.variables,
            parameter_dependencies=deps.parameters,
            entity=entity,
            definition_period=getattr(var_class, "definition_period", "year"),
            value_type=getattr(var_class, "value_type", float),
            default_value=getattr(var_class, "default_value", 0),
            is_input=is_input,
        )

        # Add dependencies to process queue
        for dep in deps.variables:
            if dep not in processed:
                to_process.append(dep)
                all_var_names.add(dep)

        # Collect parameter paths
        all_param_paths.update(deps.parameters)

    # Extract parameter values
    parameters = {}
    if all_param_paths:
        try:
            params = system.parameters
            all_params = extract_parameter_tree(params, instant)

            # Filter to only the parameters we need
            for path in all_param_paths:
                if path in all_params:
                    parameters[path] = all_params[path]
                else:
                    # Try to find by partial match
                    for full_path, param in all_params.items():
                        if full_path.endswith(path):
                            parameters[path] = param
                            break
        except Exception as e:
            print(f"Warning: Could not extract parameters: {e}")

    return variables, parameters


def generate_minimal_code(
    variables: dict[str, ExtractedVariable],
    parameters: dict[str, ExtractedParameter],
    target_variables: list[str],
) -> str:
    """
    Generate minimal standalone Python code for the extracted variables.

    This produces a single function that computes all target variables
    with parameters inlined as constants.
    """
    from pe_compile.generator import CodeGenerator

    generator = CodeGenerator()

    # Build dependency graph for topological sort
    graph = DependencyGraph()
    for name, var in variables.items():
        graph.add_variable(
            name=name,
            dependencies=list(var.dependencies),
            formula_source=var.formula_source,
            entity=var.entity,
            definition_period=var.definition_period,
            value_type=var.value_type,
            default_value=var.default_value,
            is_input=var.is_input,
        )

    # Get sorted order
    sorted_vars = graph.topological_sort(target_variables)

    # Add variables to generator in order
    for var_name in sorted_vars:
        if var_name not in variables:
            continue

        var = variables[var_name]

        if var.is_input:
            generator.add_input_variable(
                name=var_name,
                default_value=var.default_value,
                value_type=var.value_type,
            )
        else:
            generator.add_variable(
                name=var_name,
                formula_source=var.formula_source,
                dependencies=list(var.dependencies),
            )

    # Add parameter values
    for path, param in parameters.items():
        value = param.value
        # Handle numpy arrays and other types
        if hasattr(value, "item"):
            value = value.item()
        elif hasattr(value, "__float__"):
            value = float(value)
        generator.add_parameter(path, value)

    return generator.generate_module()
