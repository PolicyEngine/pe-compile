# Performance Benchmarks

This page presents performance comparisons between full PolicyEngine and pe-compile generated code.

## Test Setup

- **Hardware**: Apple M1 MacBook Pro
- **Python**: 3.13
- **PolicyEngine-UK**: 2.59.0
- **Test**: UK income tax calculation for single person

## Startup Time

| Approach | Time | Speedup |
|----------|------|---------|
| PolicyEngine-UK | 12,000 ms | 1x |
| pe-compile output | <1 ms | **12,000x** |

PolicyEngine must load thousands of YAML parameters and Python variables on startup. The compiled calculator has everything inlined.

## Single Calculation

| Approach | Time per calculation | Speedup |
|----------|---------------------|---------|
| PolicyEngine-UK | 516 ms | 1x |
| pe-compile output | 0.001 ms | **516,000x** |

Each PolicyEngine calculation creates a new Simulation object, loads relevant variables, and traces the dependency graph. The compiled code executes direct Python operations.

## Batch Calculation (1,000 households)

| Approach | Total time | Per household | Speedup |
|----------|------------|---------------|---------|
| PolicyEngine-UK | ~617 sec (projected) | 617 ms | 1x |
| pe-compile output | 0.9 ms | 0.001 ms | **695,000x** |

For batch processing, the speedup is similar since each PolicyEngine calculation is independent.

## Memory Usage

| Approach | Size |
|----------|------|
| PolicyEngine-UK package | ~50 MB |
| pe-compile output | ~2 KB |

The compiled calculator is just a few kilobytes of Python code.

## Code Generation Time

Generating the standalone calculator takes ~10ms:

```
Code generation time: 10.5ms
```

This is a one-time cost that produces a permanent artifact.

## Benchmark Code

```python
"""Run this to reproduce benchmarks."""
import time
import numpy as np

# ========== STANDALONE CALCULATOR ==========
from pe_compile import CodeGenerator

generator = CodeGenerator()
generator.add_input_variable("employment_income", default_value=0)
generator.add_parameter("personal_allowance", 12570)
generator.add_parameter("basic_rate", 0.20)
generator.add_parameter("basic_rate_limit", 37700)

generator.add_variable(
    name="taxable_income",
    formula_source="""
def formula(person, period, parameters):
    income = person("employment_income", period)
    pa = parameters(period).personal_allowance
    return max(0, income - pa)
""",
    dependencies=["employment_income"],
)

generator.add_variable(
    name="income_tax",
    formula_source="""
def formula(person, period, parameters):
    taxable = person("taxable_income", period)
    rate = parameters(period).basic_rate
    limit = parameters(period).basic_rate_limit
    return min(taxable, limit) * rate
""",
    dependencies=["taxable_income"],
)

code = generator.generate_module()
ns = {}
exec(code, ns)
standalone_calculate = ns["calculate"]

# ========== POLICYENGINE ==========
from policyengine_uk import Simulation

def pe_calculate(employment_income):
    sim = Simulation(situation={
        "people": {"person": {"employment_income": {2024: employment_income}}},
        "households": {"household": {"members": ["person"]}},
    })
    return {"income_tax": float(sim.calculate("income_tax", 2024)[0])}

# ========== BENCHMARK ==========
# Standalone
n = 100
times = []
for _ in range(n):
    start = time.time()
    standalone_calculate(employment_income=50000)
    times.append(time.time() - start)
print(f"Standalone: {sum(times)/len(times)*1000:.3f}ms avg")

# PolicyEngine
times = []
for _ in range(10):
    start = time.time()
    pe_calculate(50000)
    times.append(time.time() - start)
print(f"PolicyEngine: {sum(times)/len(times)*1000:.1f}ms avg")
```

## Why So Fast?

### No Framework Overhead

PolicyEngine uses OpenFisca's framework which provides:
- Dynamic variable resolution
- Period handling
- Entity relationships
- Reform support
- Tracing and debugging

The compiled code has none of this - it's pure Python arithmetic.

### Inlined Parameters

Instead of loading YAML files and traversing parameter trees:

```python
# PolicyEngine (at runtime)
pa = parameters(period).gov.hmrc.income_tax.allowances.personal_allowance

# Compiled (constant)
pa = 12570
```

### No Object Creation

Each PolicyEngine calculation creates:
- Simulation object
- Entity holders
- Period objects
- Variable holders

The compiled code creates one dictionary.

### Minimal Dependencies

```python
# PolicyEngine
import policyengine_uk  # ~50MB, 20+ transitive deps

# Compiled
import numpy as np  # Only if needed for vectorization
```

## When to Use Which

| Use Case | Recommendation |
|----------|----------------|
| Policy research | Full PolicyEngine |
| Interactive tools | pe-compile |
| Batch processing (millions) | pe-compile |
| Reform analysis | Full PolicyEngine |
| Embedded/mobile | pe-compile |
| API backend | Either (depends on throughput) |
