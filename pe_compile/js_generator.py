"""
JavaScript/TypeScript code generation from PolicyEngine formulas.

This module generates standalone JS code that can run in browsers
or Node.js without any Python dependencies - perfect for static sites.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional


def python_to_js_expression(expr: str) -> str:
    """
    Convert a Python expression to JavaScript.

    Handles common patterns:
    - np.maximum/minimum -> Math.max/min
    - where(cond, a, b) -> (cond) ? (a) : (b)
    - True/False -> true/false
    - // -> Math.floor division
    - ** -> ** (ES2016)
    """
    result = expr

    # Convert numpy functions to Math equivalents
    numpy_to_math = {
        r"np\.maximum\s*\(": "Math.max(",
        r"np\.minimum\s*\(": "Math.min(",
        r"np\.ceil\s*\(": "Math.ceil(",
        r"np\.floor\s*\(": "Math.floor(",
        r"np\.abs\s*\(": "Math.abs(",
        r"np\.sqrt\s*\(": "Math.sqrt(",
        r"np\.round\s*\(": "Math.round(",
        r"np\.exp\s*\(": "Math.exp(",
        r"np\.log\s*\(": "Math.log(",
    }

    for pattern, replacement in numpy_to_math.items():
        result = re.sub(pattern, replacement, result)

    # Convert Python builtins
    result = re.sub(r"\bmax\s*\(", "Math.max(", result)
    result = re.sub(r"\bmin\s*\(", "Math.min(", result)
    result = re.sub(r"\babs\s*\(", "Math.abs(", result)
    result = re.sub(r"\bround\s*\(", "Math.round(", result)

    # Convert where() and np.where() to ternary
    # This needs to handle nested where() calls
    while "where(" in result or "np.where(" in result:
        result = _convert_where_to_ternary(result)

    # Convert boolean literals
    result = re.sub(r"\bTrue\b", "true", result)
    result = re.sub(r"\bFalse\b", "false", result)
    result = re.sub(r"\bNone\b", "null", result)

    # Convert floor division // to Math.floor(a / b)
    result = re.sub(
        r"(\w+|\([^)]+\))\s*//\s*(\w+|\([^)]+\))",
        r"Math.floor(\1 / \2)",
        result,
    )

    # max_ and min_ (PE aliases)
    result = re.sub(r"\bmax_\s*\(", "Math.max(", result)
    result = re.sub(r"\bmin_\s*\(", "Math.min(", result)

    return result


def _convert_where_to_ternary(expr: str) -> str:
    """Convert a single where(cond, a, b) to (cond) ? (a) : (b)."""
    # Match where( or np.where(
    pattern = r"(?:np\.)?where\s*\("

    match = re.search(pattern, expr)
    if not match:
        return expr

    start = match.start()
    paren_start = match.end() - 1  # Position of opening paren

    # Find matching closing paren and split by commas at depth 1
    depth = 0
    args = []
    current_arg_start = paren_start + 1
    i = paren_start

    while i < len(expr):
        char = expr[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                # End of where() call
                args.append(expr[current_arg_start:i].strip())
                break
        elif char == "," and depth == 1:
            args.append(expr[current_arg_start:i].strip())
            current_arg_start = i + 1
        i += 1

    if len(args) != 3:
        return expr  # Can't convert, return as-is

    cond, if_true, if_false = args
    ternary = f"(({cond}) ? ({if_true}) : ({if_false}))"

    # Replace the where() call with ternary
    end = i + 1
    return expr[:start] + ternary + expr[end:]


def generate_js_function(
    name: str,
    inputs: list[str],
    body: str,
    defaults: Optional[dict[str, Any]] = None,
    arrow: bool = False,
    typescript: bool = False,
    input_types: Optional[dict[str, str]] = None,
    return_type: Optional[str] = None,
) -> str:
    """
    Generate a JavaScript function.

    Args:
        name: Function name
        inputs: List of input parameter names
        body: Function body (JS code)
        defaults: Default values for parameters
        arrow: Generate arrow function syntax
        typescript: Generate TypeScript with types
        input_types: Type annotations for inputs (TS only)
        return_type: Return type annotation (TS only)

    Returns:
        JavaScript function code
    """
    defaults = defaults or {}
    input_types = input_types or {}

    # Build parameter list
    params = []
    for inp in inputs:
        param = inp
        if typescript and inp in input_types:
            param = f"{inp}: {input_types[inp]}"
        if inp in defaults:
            default_val = defaults[inp]
            if isinstance(default_val, bool):
                default_val = "true" if default_val else "false"
            elif isinstance(default_val, str):
                default_val = f'"{default_val}"'
            param = f"{param} = {default_val}"
        params.append(param)

    param_str = ", ".join(params)

    # Build return type
    ret_type = ""
    if typescript and return_type:
        ret_type = f": {return_type}"

    if arrow:
        if "\n" in body or "return" in body:
            return f"const {name} = ({param_str}){ret_type} => {{\n{body}\n}};"
        else:
            return f"const {name} = ({param_str}){ret_type} => {body};"
    else:
        return f"function {name}({param_str}){ret_type} {{\n{body}\n}}"


@dataclass
class JSInput:
    """Input variable for JS generator."""

    name: str
    default: Any = 0
    type_hint: str = "number"
    description: str = ""


@dataclass
class JSCalculation:
    """A calculation step for JS generator."""

    name: str
    expression: str
    dependencies: list[str] = field(default_factory=list)


class JSCodeGenerator:
    """
    Generator for standalone JavaScript calculators.

    Produces browser-ready JS code that can run without any backend.
    Perfect for static sites, embedded widgets, and offline tools.

    Usage:
        gen = JSCodeGenerator()
        gen.add_input("income", default=0)
        gen.add_calculation("tax", "income * 0.2")
        code = gen.generate()
    """

    def __init__(
        self,
        module_type: str = "esm",  # "esm", "commonjs", "iife", "none"
        typescript: bool = False,
        include_jsdoc: bool = True,
    ):
        self.module_type = module_type
        self.typescript = typescript
        self.include_jsdoc = include_jsdoc
        self.inputs: dict[str, JSInput] = {}
        self.calculations: list[JSCalculation] = []

    def add_input(
        self,
        name: str,
        default: Any = 0,
        type_hint: str = "number",
        description: str = "",
    ) -> None:
        """Add an input variable."""
        self.inputs[name] = JSInput(
            name=name,
            default=default,
            type_hint=type_hint,
            description=description,
        )

    def add_calculation(
        self,
        name: str,
        expression: str,
        dependencies: Optional[list[str]] = None,
    ) -> None:
        """Add a calculation step."""
        self.calculations.append(
            JSCalculation(
                name=name,
                expression=expression,
                dependencies=dependencies or [],
            )
        )

    def add_from_python_formula(
        self,
        name: str,
        formula_source: str,
        inputs: list[str],
        parameters: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Add a calculation from a Python PE formula.

        Converts Python syntax to JavaScript.
        """
        parameters = parameters or {}

        # Extract the formula body
        lines = formula_source.strip().split("\n")
        body_lines = []
        in_body = False

        for line in lines:
            if line.strip().startswith("def formula"):
                in_body = True
                continue
            if in_body and line.strip():
                body_lines.append(line.strip())

        body = "\n".join(body_lines)

        # Replace entity variable access with direct variable names
        # person("var", period) -> var
        entity_pattern = (
            r"(?:person|household|tax_unit|family|benunit|state)"
            r'\s*\(\s*["\'](\w+)["\']\s*,\s*\w+\s*\)'
        )
        body = re.sub(entity_pattern, r"\1", body)

        # Inline parameter values
        for param_name, value in parameters.items():
            body = re.sub(rf"\b{re.escape(param_name)}\b", str(value), body)

        # Convert to JS expression
        body = python_to_js_expression(body)

        # Handle return statement
        if "return " in body:
            # Extract just the expression after return
            return_match = re.search(r"return\s+(.+)$", body, re.MULTILINE)
            if return_match:
                body = return_match.group(1)

        # Add inputs
        for inp in inputs:
            if inp not in self.inputs:
                self.add_input(inp)

        # Add calculation
        self.add_calculation(name, body)

    def generate(self) -> str:
        """Generate the complete JavaScript module."""
        lines = []

        # Header comment
        lines.append("/**")
        lines.append(
            " * Auto-generated calculator from PolicyEngine formulas."
        )
        lines.append(" * Generated by pe-compile")
        lines.append(" * ")
        lines.append(" * This code runs entirely in the browser - no server")
        lines.append(" * required! Perfect for static sites and offline use.")
        lines.append(" */")
        lines.append("")

        # Build function body
        body_lines = []

        # Calculate all values
        for calc in self.calculations:
            if self.typescript:
                body_lines.append(
                    f"  const {calc.name}: number = {calc.expression};"
                )
            else:
                body_lines.append(f"  const {calc.name} = {calc.expression};")

        # Return object with all results
        result_keys = [calc.name for calc in self.calculations]
        if result_keys:
            body_lines.append("")
            body_lines.append("  return {")
            for key in result_keys:
                body_lines.append(f"    {key},")
            body_lines.append("  };")

        body = "\n".join(body_lines)

        # Build parameter list
        params = []
        for name, inp in self.inputs.items():
            if self.typescript:
                param = f"{name}: {inp.type_hint} = {inp.default}"
            else:
                param = f"{name} = {inp.default}"
            params.append(param)

        param_str = ", ".join(params)

        # JSDoc if enabled
        if self.include_jsdoc and not self.typescript:
            lines.append("/**")
            lines.append(" * Calculate tax and benefit values.")
            lines.append(" *")
            for name, inp in self.inputs.items():
                desc = inp.description or f"Input value for {name}"
                lines.append(f" * @param {{{inp.type_hint}}} {name} - {desc}")
            lines.append(
                " * @returns {Object} Object containing all calculated values"
            )
            lines.append(" */")

        # Function signature
        if self.typescript:
            return_type = (
                "{ "
                + ", ".join(f"{c.name}: number" for c in self.calculations)
                + " }"
            )
            lines.append(f"function calculate({param_str}): {return_type} {{")
        else:
            lines.append(f"function calculate({param_str}) {{")

        lines.append(body)
        lines.append("}")
        lines.append("")

        # Module export
        if self.module_type == "esm":
            lines.append("export { calculate };")
            lines.append("export default calculate;")
        elif self.module_type == "commonjs":
            lines.append("module.exports = { calculate };")
        elif self.module_type == "iife":
            # Wrap everything in IIFE for global scope
            all_code = "\n".join(lines)
            lines = [
                "(function(global) {",
                all_code,
                "  global.calculate = calculate;",
                "})(typeof window !== 'undefined' ? window : global);",
            ]

        return "\n".join(lines)

    def generate_html_demo(self, title: str = "Calculator") -> str:
        """
        Generate a complete HTML page with the calculator.

        Perfect for quick demos and static hosting.
        """
        js_code = self.generate()

        # Remove module exports for inline use
        js_code = js_code.replace("export { calculate };", "")
        js_code = js_code.replace("export default calculate;", "")

        input_fields = []
        for name, inp in self.inputs.items():
            input_fields.append(
                f"""
      <div class="field">
        <label for="{name}">{name.replace('_', ' ').title()}</label>
        <input type="number" id="{name}" value="{inp.default}"
               oninput="updateResults()">
      </div>"""
            )

        result_fields = []
        for calc in self.calculations:
            result_fields.append(
                f"""
      <div class="result">
        <span class="label">{calc.name.replace('_', ' ').title()}</span>
        <span class="value" id="result_{calc.name}">0</span>
      </div>"""
            )

        # Build update function
        input_reads = ", ".join(
            f"{name}: parseFloat(document.getElementById('{name}').value) || 0"
            for name in self.inputs.keys()
        )
        result_updates = "\n    ".join(
            f"document.getElementById('result_{c.name}').textContent = "
            f"results.{c.name}.toFixed(2);"
            for c in self.calculations
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 500px;
      margin: 2rem auto;
      padding: 1rem;
      background: #f5f5f5;
    }}
    h1 {{ color: #2d4a3e; margin-bottom: 1.5rem; }}
    .field {{
      margin-bottom: 1rem;
    }}
    label {{
      display: block;
      font-weight: 500;
      margin-bottom: 0.25rem;
      color: #333;
    }}
    input {{
      width: 100%;
      padding: 0.75rem;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 1rem;
    }}
    input:focus {{
      outline: none;
      border-color: #2d4a3e;
    }}
    .results {{
      background: white;
      padding: 1.5rem;
      border-radius: 8px;
      margin-top: 1.5rem;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    .result {{
      display: flex;
      justify-content: space-between;
      padding: 0.75rem 0;
      border-bottom: 1px solid #eee;
    }}
    .result:last-child {{ border-bottom: none; }}
    .result .label {{ color: #666; }}
    .result .value {{
      font-weight: 600;
      color: #2d4a3e;
    }}
    .powered-by {{
      text-align: center;
      margin-top: 2rem;
      font-size: 0.85rem;
      color: #999;
    }}
    .powered-by a {{ color: #2d4a3e; }}
  </style>
</head>
<body>
  <h1>{title}</h1>

  <div class="inputs">
    {"".join(input_fields)}
  </div>

  <div class="results">
    {"".join(result_fields)}
  </div>

  <p class="powered-by">
    Powered by <a href="https://policyengine.org">PolicyEngine</a> |
    Compiled with <a href="https://github.com/PolicyEngine/pe-compile">pe-compile</a>
  </p>

  <script>
{js_code}

function updateResults() {{
  const results = calculate({{ {input_reads} }});
  {result_updates}
}}

// Initial calculation
updateResults();
  </script>
</body>
</html>"""

        return html
