"""
pe-compile: Compile PolicyEngine country models into standalone calculators.

This package extracts variable formulas and parameter values from PolicyEngine
country models and generates standalone Python modules that can run without
the full PolicyEngine framework.
"""

__version__ = "0.1.0"

from pe_compile.generator import (
    CodeGenerator,
    generate_standalone_function,
    inline_parameters,
)
from pe_compile.graph import (
    Dependencies,
    DependencyGraph,
    VariableInfo,
    build_dependency_graph,
    extract_dependencies_from_formula,
)

__all__ = [
    "DependencyGraph",
    "VariableInfo",
    "Dependencies",
    "extract_dependencies_from_formula",
    "build_dependency_graph",
    "CodeGenerator",
    "generate_standalone_function",
    "inline_parameters",
]
