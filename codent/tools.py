from pathlib import Path

MAX_READ_CHARS = 20_000


class ToolError(Exception):
    pass


def _resolve(root: Path, path: str) -> Path:
    full = (root / path).resolve()
    if full != root and root not in full.parents:
        raise ToolError(f"path escapes project root: {path}")
    return full


def list_dir(root: Path, path: str = ".") -> str:
    full = _resolve(root, path)
    if not full.is_dir():
        raise ToolError(f"not a directory: {path}")
    entries = sorted(full.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    return "\n".join(p.name + ("/" if p.is_dir() else "") for p in entries) or "(empty)"


def read_file(root: Path, path: str) -> str:
    full = _resolve(root, path)
    if not full.is_file():
        raise ToolError(f"not a file: {path}")
    try:
        text = full.read_text()
    except UnicodeDecodeError:
        raise ToolError(f"not a text file: {path}")
    truncated = len(text) > MAX_READ_CHARS
    lines = text[:MAX_READ_CHARS].splitlines()
    out = "\n".join(f"{i}\t{line}" for i, line in enumerate(lines, 1))
    return out + ("\n... (truncated)" if truncated else "")


TOOL_FUNCS = {"list_dir": list_dir, "read_file": read_file}

TOOL_SCHEMAS = [
    {
        "name": "list_dir",
        "description": "List files and folders in a directory (folders end with /).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory, relative to project root. Default '.'"}},
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path relative to project root."}},
            "required": ["path"],
        },
    },
]


def run_tool(root: Path, name: str, args: dict) -> tuple[str, bool]:
    """Returns (output, is_error)."""
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        return f"unknown tool: {name}", True
    try:
        return fn(root, **args), False
    except ToolError as e:
        return str(e), True
    except TypeError as e:
        return f"bad arguments: {e}", True
