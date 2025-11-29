"""
Reform support for pe-compile.

This module handles:
1. Parsing reform specifications (JSON or dict format)
2. Applying reforms to parameter values
3. Integrating with the compilation process
"""

import json
from typing import Any


def parse_reform_json(reform_json: str) -> dict[str, Any]:
    """
    Parse a JSON string specifying parameter overrides.

    Format: {"parameter.path": value, ...}

    Args:
        reform_json: JSON string with parameter path -> value mappings

    Returns:
        Dictionary mapping parameter paths to values

    Raises:
        ValueError: If JSON is invalid
    """
    try:
        return json.loads(reform_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid reform JSON: {e}")


def parse_reform_dict(
    reform_dict: dict[str, dict[str, Any]],
    year: int,
) -> dict[str, Any]:
    """
    Parse a PolicyEngine-style reform dictionary.

    PE reforms have format:
    {
        "parameter.path": {
            "2024-01-01": value,
            "2025-01-01": other_value,
        }
    }

    Args:
        reform_dict: PolicyEngine-style reform dictionary
        year: Year to extract values for

    Returns:
        Dictionary mapping parameter paths to values for the given year
    """
    result = {}
    target_date = f"{year}-01-01"

    for param_path, date_values in reform_dict.items():
        if not isinstance(date_values, dict):
            # Simple value, not date-keyed
            result[param_path] = date_values
            continue

        # Find the applicable value for this year
        # Sort dates and find the latest one <= target_date
        sorted_dates = sorted(date_values.keys())
        applicable_value = None

        for date_str in sorted_dates:
            if date_str <= target_date:
                applicable_value = date_values[date_str]
            else:
                break

        if applicable_value is not None:
            result[param_path] = applicable_value

    return result


def apply_reform_to_parameters(
    base_params: dict[str, Any],
    reform: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply reform overrides to base parameter values.

    Args:
        base_params: Original parameter values
        reform: Parameter overrides to apply

    Returns:
        New dictionary with reformed values (base_params unchanged)
    """
    # Create a copy to avoid modifying the original
    result = dict(base_params)

    # Apply overrides
    for path, value in reform.items():
        result[path] = value

    return result
