# pe-compile

Compile PolicyEngine country models into fast standalone calculators.

## Overview

`pe-compile` extracts variable formulas and parameter values from PolicyEngine country models (like `policyengine-uk` or `policyengine-us`) and generates standalone Python modules that can run **50-150x faster** than the full framework.

This is useful for:
- **Interactive tools** that need sub-second response times
- **Embedded calculators** with minimal dependencies
- **Edge deployments** where the full PE stack is too heavy
- **WebAssembly** compilation targets

## Installation

```bash
# Base package
pip install pe-compile

# With UK model support
pip install pe-compile[uk]

# With US model support
pip install pe-compile[us]

# Development
pip install pe-compile[dev]
```

## Quick Start

### Command Line

```bash
# Compile UK income tax to standalone calculator
pe-compile --country uk --variables income_tax -o uk_tax.py

# Compile multiple variables
pe-compile --country uk --variables income_tax,national_insurance,child_benefit -o uk_calc.py

# Use specific date for parameter values
pe-compile --country uk --variables income_tax --date 2024-04-06 -o uk_tax_2024.py

# Dry run - show what would be compiled
pe-compile --country uk --variables income_tax --dry-run
```

### Python API

```python
from pe_compile import CodeGenerator, build_dependency_graph

# Build a custom calculator
generator = CodeGenerator()

generator.add_input_variable("gross_income", default_value=0)
generator.add_input_variable("pension_contributions", default_value=0)

generator.add_variable(
    name="taxable_income",
    formula_source='''
def formula(person, period):
    gross = person("gross_income", period)
    pension = person("pension_contributions", period)
    return max(gross - pension - 12570, 0)
''',
    dependencies=["gross_income", "pension_contributions"],
)

generator.add_parameter("gov.hmrc.income_tax.rates.basic", 0.20)

# Generate standalone module
code = generator.generate_module()
print(code)
```

### Using Generated Code

```python
# The generated module has a simple interface
from uk_tax import calculate

result = calculate(
    gross_income=50000,
    pension_contributions=5000,
)

print(f"Taxable income: £{result['taxable_income']:,.2f}")
print(f"Income tax: £{result['income_tax']:,.2f}")
```

## How It Works

1. **Dependency Analysis**: Parses PolicyEngine variable formulas to extract:
   - Variable dependencies (`person("other_var", period)`)
   - Parameter references (`parameters(period).gov.path.to.param`)

2. **Topological Sort**: Orders calculations so dependencies are computed first

3. **Code Generation**: Transforms PE formulas into standalone functions:
   - Replaces entity references with direct variable access
   - Inlines parameter values for the specified date
   - Preserves numpy operations for vectorization

4. **Output**: Generates a single Python file with:
   - No PolicyEngine dependencies
   - A simple `calculate(**inputs) -> dict` interface
   - All calculations in dependency order

## Performance Comparison

| Metric | PolicyEngine | pe-compile output |
|--------|-------------|-------------------|
| Startup time | 2-3 seconds | ~50ms |
| Calculation time | 10-30 seconds | 200-400ms |
| Memory usage | 200-500 MB | ~30 MB |
| Dependencies | 20+ packages | numpy only |

## Limitations

- **Snapshot in time**: Generated code has parameters frozen at a specific date
- **Subset only**: Only includes variables you explicitly request
- **No reforms**: Reform system not supported (yet)
- **Single entity**: Currently focused on person-level calculations

## Development

```bash
# Clone the repo
git clone https://github.com/PolicyEngine/pe-compile.git
cd pe-compile

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=pe_compile

# Format code
black pe_compile tests
ruff check pe_compile tests
```

## Architecture

```
pe_compile/
├── __init__.py      # Package exports
├── graph.py         # Dependency graph extraction
├── generator.py     # Code generation
└── cli.py           # Command-line interface

tests/
├── test_dependency_graph.py
├── test_code_generator.py
└── test_cli.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests first (TDD)
4. Implement the feature
5. Run `make format` and `make test`
6. Submit a PR

## License

MIT License - see LICENSE file.

## See Also

- [PolicyEngine](https://policyengine.org) - The main PolicyEngine platform
- [policyengine-core](https://github.com/PolicyEngine/policyengine-core) - Core simulation engine
- [uk-autumn-budget-lifecycle](https://github.com/PolicyEngine/uk-autumn-budget-lifecycle) - Example of a manually-optimized calculator
