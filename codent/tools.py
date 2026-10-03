import os
import re
from fnmatch import fnmatch
from pathlib import Path

MAX_READ_CHARS = 20_000
MAX_RESULTS = 100
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache"}


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


def _walk_files(base: Path):
    """Yield files under base, skipping noisy directories."""
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def find_files(root: Path, pattern: str, path: str = ".") -> str:
    base = _resolve(root, path)
    if not base.is_dir():
        raise ToolError(f"not a directory: {path}")
    matches = []
    for f in _walk_files(base):
        rel = f.relative_to(root).as_posix()
        if fnmatch(f.name, pattern) or fnmatch(rel, pattern):
            matches.append(rel)
    return _cap(matches)


def search(root: Path, pattern: str, path: str = ".", glob: str | None = None) -> str:
    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ToolError(f"invalid regex: {e}")
    base = _resolve(root, path)
    files = [base] if base.is_file() else _walk_files(base)
    hits = []
    for f in files:
        if glob and not fnmatch(f.name, glob):
            continue
        try:
            lines = f.read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable
        rel = f.relative_to(root).as_posix()
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                if len(hits) > MAX_RESULTS:
                    return _cap(hits)
    return _cap(hits)


def _cap(items: list[str]) -> str:
    if not items:
        return "(no matches)"
    shown = items[:MAX_RESULTS]
    out = "\n".join(shown)
    if len(items) > MAX_RESULTS:
        out += f"\n... (more than {MAX_RESULTS} results, narrow your search)"
    return out


TOOL_FUNCS = {
    "list_dir": list_dir,
    "read_file": read_file,
    "find_files": find_files,
    "search": search,
}

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
    {
        "name": "find_files",
        "description": "Find files by name pattern (e.g. '*.py' or 'tests/*.py'). Skips .git, .venv, node_modules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern matched against file name or relative path."},
                "path": {"type": "string", "description": "Directory to search in. Default '.'"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "search",
        "description": "Search file contents with a regex. Returns 'file:line: text' matches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python regular expression."},
                "path": {"type": "string", "description": "File or directory to search. Default '.'"},
                "glob": {"type": "string", "description": "Only search files whose name matches, e.g. '*.py'."},
            },
            "required": ["pattern"],
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
