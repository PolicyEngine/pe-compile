# Limitations & Future Work

`pe-compile` is under active development. This page documents current limitations and planned improvements.

## Current Limitations

### Unsupported PolicyEngine Patterns

Not all PolicyEngine formula patterns are currently supported:

#### 1. Parameter-Defined Variable Lists

```python
# NOT YET SUPPORTED
def formula(person, period, parameters):
    p = parameters(period).gov.hmrc.income_tax
    additions = add(person, period, p.income_tax_additions)  # Parameter contains variable list
    return additions
```

Variables like `income_tax` use parameters that contain lists of variable names. These dynamic references require runtime resolution and aren't yet supported.

#### 2. ParameterScale Calculations

```python
# NOT YET SUPPORTED
def formula(household, period, parameters):
    wealth = household("total_wealth", period)
    tax = parameters(period).gov.contrib.wealth_tax
    return tax.calc(wealth)  # ParameterScale with brackets
```

Tax brackets and marginal rate calculations using `ParameterScale.calc()` are not yet inlined. The `calc()` method handles complex bracket lookups that need special treatment.

#### 3. Complex Aggregations

```python
# LIMITED SUPPORT
def formula(household, period):
    return household.sum(
        household.members("employment_income", period) *
        household.members("is_adult", period)
    )
```

Entity hierarchy operations (`household.sum()`, `household.any()`, etc.) are partially supported but may not work in all cases.

### Supported Patterns

These patterns are well-supported:

#### Simple Variable References
```python
def formula(person, period):
    income = person("employment_income", period)
    expenses = person("allowable_expenses", period)
    return income - expenses
```

#### Direct Parameter Access
```python
def formula(person, period, parameters):
    income = person("employment_income", period)
    rate = parameters(period).gov.tax.basic_rate  # Scalar parameter
    return income * rate
```

#### Boolean Comparisons
```python
def formula(person, period):
    return person("carers_allowance", period) > 0
```

#### NumPy Operations
```python
def formula(person, period):
    income = person("employment_income", period)
    threshold = parameters(period).gov.tax.threshold
    return np.maximum(0, income - threshold)
```

## Planned Improvements

### Short Term

1. **ParameterScale Support** - Inline tax bracket calculations as nested `where()` conditions
2. **Better Error Messages** - Clear feedback when unsupported patterns are detected
3. **Partial Compilation** - Skip unsupported variables instead of failing entirely

### Medium Term

4. **Vectorized Batch Processing** - Generate NumPy-optimized code for batch calculations
5. **JavaScript Output** - Generate JS/TS for web embedding without Python
6. **Validation Suite** - Automated testing that compiled output matches PolicyEngine

### Long Term

7. **WebAssembly Target** - Compile to WASM for portable, fast execution anywhere
8. **Incremental Compilation** - Cache and reuse unchanged variable compilations
9. **Full PE Coverage** - Support all PE patterns through code generation

## Contributing

If you encounter unsupported patterns or have ideas for improvements, please [open an issue](https://github.com/PolicyEngine/pe-compile/issues).

For patterns you need supported urgently, consider:
1. Filing an issue with the specific formula source
2. Proposing a workaround or implementation approach
3. Contributing a PR with tests
