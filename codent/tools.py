import difflib
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


def _apply_change(root: Path, path: str, new_text: str, approve) -> str:
    """Show a diff, ask for approval, then write. `approve(path, diff) -> bool`."""
    full = _resolve(root, path)
    old_text = full.read_text() if full.exists() else ""
    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    if approve is None or not approve(path, diff):
        raise ToolError(f"user declined the change to {path}; nothing was written")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(new_text)
    return f"wrote {path}"


def edit_file(root: Path, path: str, old: str, new: str, approve=None) -> str:
    full = _resolve(root, path)
    if not full.is_file():
        raise ToolError(f"not a file: {path}")
    if not old:
        raise ToolError("'old' must not be empty; use write_file to create files")
    try:
        text = full.read_text()
    except UnicodeDecodeError:
        raise ToolError(f"not a text file: {path}")
    count = text.count(old)
    if count == 0:
        raise ToolError("'old' text not found; read the file again and copy it exactly")
    if count > 1:
        raise ToolError(f"'old' text matches {count} places; include more surrounding lines to make it unique")
    return _apply_change(root, path, text.replace(old, new), approve)


def write_file(root: Path, path: str, content: str, approve=None) -> str:
    full = _resolve(root, path)
    if full.is_dir():
        raise ToolError(f"is a directory: {path}")
    return _apply_change(root, path, content, approve)


def delete_file(root: Path, path: str, approve=None) -> str:
    full = _resolve(root, path)
    if not full.is_file():
        raise ToolError(f"not a file: {path} (only files can be deleted)")
    try:
        old_text = full.read_text()
    except UnicodeDecodeError:
        old_text = None
    if old_text is None:
        diff = f"(binary file {path} will be deleted)"
    else:
        diff = "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                [],
                fromfile=f"a/{path}",
                tofile="/dev/null",
            )
        ) or f"(empty file {path} will be deleted)"
    if approve is None or not approve(path, diff):
        raise ToolError(f"user declined deleting {path}; nothing was deleted")
    full.unlink()
    return f"deleted {path}"


TOOL_FUNCS = {
    "list_dir": list_dir,
    "read_file": read_file,
    "find_files": find_files,
    "search": search,
    "edit_file": edit_file,
    "write_file": write_file,
    "delete_file": delete_file,
}
WRITE_TOOLS = {"edit_file", "write_file", "delete_file"}

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
    {
        "name": "edit_file",
        "description": (
            "Edit a file by replacing one exact piece of text. 'old' must match exactly once "
            "(include surrounding lines if needed). The user approves each change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root."},
                "old": {"type": "string", "description": "Exact existing text to replace."},
                "new": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old", "new"],
        },
    },
    {
        "name": "write_file",
        "description": "Create a new file or fully overwrite an existing one. The user approves each change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root."},
                "content": {"type": "string", "description": "Full file content."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a single file (not a directory). The user approves each deletion.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path relative to project root."}},
            "required": ["path"],
        },
    },
]


def run_tool(root: Path, name: str, args: dict, approve=None) -> tuple[str, bool]:
    """Returns (output, is_error). `approve(path, diff) -> bool` gates file writes."""
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        return f"unknown tool: {name}", True
    try:
        if name in WRITE_TOOLS:
            return fn(root, approve=approve, **args), False
        return fn(root, **args), False
    except ToolError as e:
        return str(e), True
    except TypeError as e:
        return f"bad arguments: {e}", True
