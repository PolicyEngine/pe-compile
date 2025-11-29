"""
Command-line interface for pe-compile.

Usage:
    pe-compile --country uk --variables income_tax -o calc.py
"""

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
        # Return a mock system for testing
        return create_mock_system()

    if country == "uk":
        try:
            from policyengine_uk import CountryTaxBenefitSystem

            return CountryTaxBenefitSystem()
        except ImportError:
            raise click.ClickException(
                "policyengine-uk not installed. "
                "Install with: pip install pe-compile[uk]"
            )

    if country == "us":
        try:
            from policyengine_us import CountryTaxBenefitSystem

            return CountryTaxBenefitSystem()
        except ImportError:
            raise click.ClickException(
                "policyengine-us not installed. "
                "Install with: pip install pe-compile[us]"
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

        def get_variable(self, name):
            return self.variables.get(name)

        def get_parameters(self):
            class MockParams:
                def __call__(self, instant):
                    return self

                def __getattr__(self, name):
                    return self

            return MockParams()

    return MockSystem()


def get_parameter_value(system, path: str, instant: str) -> float:
    """Get a parameter value at a specific instant."""
    try:
        params = system.get_parameters()(instant)
        for part in path.split("."):
            params = getattr(params, part)
        return float(params)
    except (AttributeError, TypeError):
        return 0.0


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
    "--date",
    "-d",
    default=None,
    help="Date for parameter values (YYYY-MM-DD, default: today)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be compiled without generating code",
)
@click.version_option(version=__version__)
def main(
    country: str,
    variables: str,
    output: Optional[str],
    date: Optional[str],
    dry_run: bool,
) -> None:
    """
    Compile PolicyEngine variables into fast standalone calculators.

    Examples:

        pe-compile --country uk --variables income_tax -o tax_calc.py

        pe-compile --country us --variables income_tax,eitc --date 2024-01-01

        pe-compile --country uk --variables ni --dry-run
    """
    # Parse variables
    var_names = [v.strip() for v in variables.split(",")]

    # Load country system
    try:
        system = load_country_system(country)
    except Exception as e:
        raise click.ClickException(str(e))

    # Get instant for parameter values
    if date:
        instant = date
    else:
        instant = str(date.today()) if hasattr(date, "today") else "2024-01-01"

    # Build dependency graph
    click.echo(f"Analyzing {len(var_names)} variable(s)...", err=True)

    # Collect all variables we need
    all_vars = {}
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
            import inspect

            try:
                source = inspect.getsource(var_class.formula)
                deps = extract_dependencies_from_formula(source)
                for dep in deps.variables:
                    if dep not in processed:
                        to_process.append(dep)
            except (TypeError, OSError):
                pass

    click.echo(
        f"Found {len(all_vars)} total variable(s) including dependencies",
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
                click.echo(f"  {var}: depends on [{deps}]")
        return

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
            for param_path in info.parameter_dependencies:
                if param_path not in generator.parameters:
                    value = get_parameter_value(system, param_path, instant)
                    generator.add_parameter(param_path, value)

    # Generate module
    code = generator.generate_module()

    # Output
    if output:
        with open(output, "w") as f:
            f.write(code)
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(code)


if __name__ == "__main__":
    main()
