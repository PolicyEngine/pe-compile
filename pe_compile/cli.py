"""
Command-line interface for pe-compile.

Usage:
    pe-compile -c uk -v income_tax --year 2024 -o calc.py
    pe-compile -c uk -v income_tax --reform '{"path": 0.25}'
"""

import inspect
from datetime import date as date_module
from typing import Optional

import click

from pe_compile import __version__
from pe_compile.generator import CodeGenerator
from pe_compile.graph import (
    build_dependency_graph,
    extract_dependencies_from_formula,
)


def load_country_system(country: str):
    """Load a PolicyEngine country tax-benefit system."""
    if country == "mock":
        return create_mock_system()

    if country == "uk":
        try:
            from policyengine_uk import CountryTaxBenefitSystem

            return CountryTaxBenefitSystem()
        except ImportError:
            raise click.ClickException(
                "policyengine-uk not installed. "
                "Install with: uv add pe-compile[uk]"
            )

    if country == "us":
        try:
            from policyengine_us import CountryTaxBenefitSystem

            return CountryTaxBenefitSystem()
        except ImportError:
            raise click.ClickException(
                "policyengine-us not installed. "
                "Install with: uv add pe-compile[us]"
            )

    raise click.ClickException(f"Unknown country: {country}")


def create_mock_system():
    """Create a mock system for testing."""

    class MockVariable:
        __name__ = "test_var"

        class entity:
            key = "person"

        definition_period = "year"
        value_type = float
        default_value = 0

        def formula(self, person, period):
            return person("input_var", period) * 2

    class MockInputVar:
        __name__ = "input_var"

        class entity:
            key = "person"

        definition_period = "year"
        value_type = float
        default_value = 0

    class MockSystem:
        variables = {
            "test_var": MockVariable,
            "input_var": MockInputVar,
        }
        parameters = None

        def get_variable(self, name):
            return self.variables.get(name)

    return MockSystem()


def get_parameter_value(params, path: str) -> Optional[float]:
    """
    Get a parameter value by path.

    Handles nested attribute access like 'gov.hmrc.income_tax.rates.basic'.
    """
    try:
        node = params
        for part in path.split("."):
            node = getattr(node, part)

        # Handle different parameter types
        if hasattr(node, "item"):
            return node.item()
        elif isinstance(node, (int, float)):
            return float(node)
        elif hasattr(node, "__float__"):
            return float(node)
        return node
    except (AttributeError, TypeError):
        return None


@click.command()
@click.option(
    "--country",
    "-c",
    required=True,
    help="Country code (uk, us, or mock for testing)",
)
@click.option(
    "--variables",
    "-v",
    required=True,
    help="Comma-separated list of variables to compile",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (stdout if not specified)",
)
@click.option(
    "--year",
    "-y",
    type=int,
    default=None,
    help="Tax year for parameter values (e.g., 2024). Default: current year",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be compiled without generating code",
)
@click.option(
    "--strip-comments",
    is_flag=True,
    default=True,
    help="Strip comments from generated code (default: True)",
)
@click.version_option(version=__version__)
def main(
    country: str,
    variables: str,
    output: Optional[str],
    year: Optional[int],
    dry_run: bool,
    strip_comments: bool,
) -> None:
    """
    Compile PolicyEngine variables into fast standalone calculators.

    Examples:

        pe-compile -c uk -v income_tax --year 2024 -o uk_tax.py

        pe-compile -c us -v income_tax,eitc --year 2024

        pe-compile -c uk -v national_insurance --dry-run
    """
    # Parse variables
    var_names = [v.strip() for v in variables.split(",")]

    # Load country system
    try:
        system = load_country_system(country)
    except Exception as e:
        raise click.ClickException(str(e))

    # Determine year
    if year is None:
        year = date_module.today().year

    instant = f"{year}-01-01"
    click.echo(f"Compiling for year {year}...", err=True)

    # Build dependency graph
    click.echo(f"Analyzing {len(var_names)} variable(s)...", err=True)

    # Collect all variables we need
    all_vars = {}
    all_param_paths = set()
    to_process = list(var_names)
    processed = set()

    while to_process:
        var_name = to_process.pop()
        if var_name in processed:
            continue
        processed.add(var_name)

        var_class = system.get_variable(var_name)
        if var_class is None:
            click.echo(f"Warning: Variable '{var_name}' not found", err=True)
            continue

        all_vars[var_name] = var_class

        # Find dependencies
        if hasattr(var_class, "formula"):
            try:
                source = inspect.getsource(var_class.formula)
                deps = extract_dependencies_from_formula(source)
                for dep in deps.variables:
                    if dep not in processed:
                        to_process.append(dep)
                all_param_paths.update(deps.parameters)
            except (TypeError, OSError):
                pass

    click.echo(
        f"Found {len(all_vars)} variable(s), "
        f"{len(all_param_paths)} parameter path(s)",
        err=True,
    )

    # Build graph
    graph = build_dependency_graph(all_vars)

    if dry_run:
        click.echo("\nVariables to compile:")
        sorted_vars = graph.topological_sort(var_names)
        for var in sorted_vars:
            if var in graph.variables:
                info = graph.variables[var]
                deps = ", ".join(info.dependencies) or "(none)"
                is_input = "INPUT" if info.is_input else "CALC"
                click.echo(f"  [{is_input}] {var}: depends on [{deps}]")

        if all_param_paths:
            click.echo("\nParameters referenced:")
            for path in sorted(all_param_paths):
                click.echo(f"  {path}")
        return

    # Get parameter values for the specified year
    click.echo("Extracting parameter values...", err=True)
    param_values = {}

    if system.parameters is not None:
        try:
            params_at_instant = system.parameters(instant)

            for path in all_param_paths:
                value = get_parameter_value(params_at_instant, path)
                if value is not None:
                    param_values[path] = value
                else:
                    click.echo(
                        f"Warning: Could not get value for {path}",
                        err=True,
                    )
        except Exception as e:
            click.echo(f"Warning: Error getting parameters: {e}", err=True)

    click.echo(
        f"Extracted {len(param_values)} parameter value(s)",
        err=True,
    )

    # Generate code
    click.echo("Generating standalone calculator...", err=True)

    generator = CodeGenerator()

    # Add all variables
    sorted_vars = graph.topological_sort(var_names)
    for var_name in sorted_vars:
        if var_name not in graph.variables:
            continue

        info = graph.variables[var_name]

        if info.is_input or not info.formula_source.strip():
            generator.add_input_variable(
                name=var_name,
                default_value=info.default_value,
                value_type=info.value_type,
            )
        else:
            generator.add_variable(
                name=var_name,
                formula_source=info.formula_source,
                dependencies=list(info.dependencies),
            )

    # Add parameter values
    for path, value in param_values.items():
        generator.add_parameter(path, value)

    # Generate module with metadata
    code = generator.generate_module()

    # Add header comment with compilation info
    header = f'''"""
Standalone calculator compiled from PolicyEngine {country.upper()}.

Generated by pe-compile v{__version__}
Year: {year}
Target variables: {", ".join(var_names)}
Total variables: {len(all_vars)}
Parameters: {len(param_values)}
"""

'''
    code = header + code.split('"""', 2)[-1].lstrip()

    # Output
    if output:
        with open(output, "w") as f:
            f.write(code)
        click.echo(f"Written to {output}", err=True)
        click.echo(f"Code size: {len(code):,} bytes", err=True)
    else:
        click.echo(code)


if __name__ == "__main__":
    main()
