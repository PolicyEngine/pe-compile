# pe-compile

**Compile PolicyEngine country models into fast standalone calculators.**

`pe-compile` extracts variable formulas and parameter values from PolicyEngine country models and generates standalone Python modules that run **up to 790,000x faster** than the full framework.

## Why pe-compile?

PolicyEngine's full microsimulation framework is powerful but heavy:
- ~12 seconds startup time
- ~500ms per calculation
- 50MB+ dependencies

For interactive tools, embedded calculators, or high-throughput batch processing, this overhead is prohibitive. `pe-compile` generates minimal, dependency-free Python code that:

- **Starts instantly** (~1ms)
- **Calculates in microseconds** (~0.001ms per household)
- **Requires only numpy** (or nothing at all)

## Quick Example

```bash
# Install with UK model support
pip install pe-compile[uk]

# Compile income tax calculator for 2024
pe-compile -c uk -v income_tax --year 2024 -o uk_tax.py
```

This generates a standalone Python file:

```python
# uk_tax.py - ~2KB, no PolicyEngine dependencies

def calculate(employment_income=0, ...):
    """Calculate income tax."""
    results = {}
    # ... all calculations inlined
    return results
```

## Use Cases

- **Interactive web calculators** (like uk-autumn-budget-lifecycle)
- **Mobile apps** with offline capability
- **High-frequency trading** tax impact estimation
- **Monte Carlo simulations** requiring millions of calculations
- **Edge deployment** (IoT, serverless, WebAssembly)

## Contents

- [Getting Started](getting-started.md)
- [Benchmarks](benchmarks.md)
- [API Reference](api.md)
