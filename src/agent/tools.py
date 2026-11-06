"""Tool definitions. To add a tool: write a function with type hints + docstring and decorate it with @tool.
The docstring becomes the tool description the LLM sees; type hints become the JSON schema."""
import ast
import inspect
import json
import os
import operator
from datetime import datetime
from pathlib import Path

WORKSPACE = Path("workspace")  # file tools are restricted to this folder
WORKSPACE.mkdir(exist_ok=True)

_TYPES = {int: "integer", float: "number", str: "string", bool: "boolean"}
_REGISTRY: dict = {}


def tool(fn):
    """Register a function as an LLM-callable tool."""
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = {"type": _TYPES.get(p.annotation, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    _REGISTRY[fn.__name__] = {
        "fn": fn,
        "schema": {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": inspect.getdoc(fn),
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        },
    }
    return fn


def get_schemas() -> list:
    return [t["schema"] for t in _REGISTRY.values()]


def call_tool(name: str, arguments: str) -> str:
    """Run a tool by name with JSON-string arguments. Errors are returned as text so the LLM can recover."""
    if name not in _REGISTRY:
        return f"Error: unknown tool '{name}'"
    try:
        return str(_REGISTRY[name]["fn"](**json.loads(arguments or "{}")))
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


# ----------------------------- Tools -----------------------------

@tool
def get_current_time() -> str:
    """Get the current local date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv, ast.USub: operator.neg}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression, e.g. '(12 + 3) * 4 / 5'. Supports + - * / // % **."""
    return str(_eval(ast.parse(expression, mode="eval").body))


def _safe_path(filename: str) -> Path:
    path = (WORKSPACE / filename).resolve()
    if not path.is_relative_to(WORKSPACE.resolve()):
        raise ValueError("path is outside the workspace")
    return path


@tool
def list_files() -> str:
    """List all files in the workspace folder."""
    files = [str(p.relative_to(WORKSPACE)) for p in WORKSPACE.rglob("*") if p.is_file()]
    return "\n".join(files) or "(workspace is empty)"


@tool
def read_file(filename: str) -> str:
    """Read the text content of a file in the workspace."""
    return _safe_path(filename).read_text(encoding="utf-8")


@tool
def write_file(filename: str, content: str) -> str:
    """Create or overwrite a text file in the workspace."""
    path = _safe_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {filename}"

# Defined Tools

@tool
def get_model_prompt_by_ID(model_id: int)-> str:
    """
    Get the model prompt from the database by model ID.
    """
    from src.agent.db_op import get_db_connection, get_model_prompt
    
    db_server = os.getenv("DB_SERVER")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    conn = get_db_connection(db_server, db_name, db_user, db_password)
    return get_model_prompt(conn, model_id)
    