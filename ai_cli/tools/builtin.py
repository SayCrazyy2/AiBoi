"""
Built-in tools. Each tool is a (ToolSpec, handler) pair. Handlers take a
dict of arguments and return a plain string result. Handlers raise
ToolExecutionError on failure; the caller turns that into a tool_result
with is_error=True so the model can see and react to it.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..providers.base import ToolSpec


class ToolExecutionError(RuntimeError):
    pass


ToolHandler = Callable[[Dict[str, Any]], str]


def _safe_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _command_allowed(command: str, allowed: Optional[List[str]]) -> bool:
    """
    If *allowed* is None or empty, everything is permitted.
    Otherwise the first token of *command* must match (by prefix) one of
    the entries in the allowlist.  Examples:
      allowed = ["ls", "cat"]  ->  "ls -la"  ✅   "rm -rf /"  ❌
      allowed = []             ->  everything  ✅
      allowed = None           ->  everything  ✅
    """
    if not allowed:
        return True
    try:
        first = shlex.split(command, comments=True)[0]
    except Exception:
        first = command.strip().split()[0] if command.strip() else ""
    first = os.path.basename(first)
    return any(first == cmd or first.endswith("/" + cmd) for cmd in allowed)


# ---------------------------------------------------------------------------
# edit_file helpers
# ---------------------------------------------------------------------------

_EDIT_MAX_FILE_SIZE = 5_000_000  # 5 MB safety cap for reading


def _preview_lines(text: str, center_line: int, radius: int = 3) -> str:
    """Return a numbered snippet of *text* centered on *center_line* (1-indexed)."""
    lines = text.splitlines()
    start = max(0, center_line - 1 - radius)
    end = min(len(lines), center_line + radius)
    out = []
    for i in range(start, end):
        marker = ">>" if (i + 1) == center_line else "  "
        out.append(f"{marker} {i + 1:>5} │ {lines[i]}")
    return "\n".join(out)


def _find_line_number(text: str, search: str) -> int:
    """Return the 1-indexed line number of the first occurrence of *search*."""
    idx = text.find(search)
    if idx == -1:
        return -1
    return text[:idx].count("\n") + 1


def make_builtin_tools(
    enable_filesystem: bool,
    enable_shell: bool,
    enable_http: bool,
    confirm_before_write: bool,
    confirm_before_shell: bool,
    confirm_fn: Callable[[str], bool],
    allowed_shell_commands: Optional[List[str]] = None,
) -> List[Tuple[ToolSpec, ToolHandler]]:
    tools: List[Tuple[ToolSpec, ToolHandler]] = []

    if enable_filesystem:
        def read_file(args: Dict[str, Any]) -> str:
            p = _safe_path(args["path"])
            if not p.exists():
                raise ToolExecutionError(f"File not found: {p}")
            try:
                text = p.read_text(errors="replace")
            except IsADirectoryError:
                raise ToolExecutionError(f"{p} is a directory, not a file")
            max_chars = 50_000
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n...[truncated, {len(text) - max_chars} more chars]"
            return text

        tools.append(
            (
                ToolSpec(
                    name="read_file",
                    description="Read the contents of a text file at the given path.",
                    input_schema={
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "File path to read"}},
                        "required": ["path"],
                    },
                ),
                read_file,
            )
        )

        def write_file(args: Dict[str, Any]) -> str:
            p = _safe_path(args["path"])
            content = args.get("content", "")
            if confirm_before_write:
                if not confirm_fn(f"Write {len(content)} chars to {p}?"):
                    raise ToolExecutionError("User declined the write.")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Wrote {len(content)} chars to {p}"

        tools.append(
            (
                ToolSpec(
                    name="write_file",
                    description="Write text content to a file, creating it (and parent directories) if needed. Overwrites existing files.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                ),
                write_file,
            )
        )

        # ---- edit_file: targeted in-place edits without rewriting the whole file ----

        def edit_file(args: Dict[str, Any]) -> str:
            """
            Supported operations:
              replace       – find `search` text, replace with `replacement` (first or all)
              insert_after  – insert `replacement` text immediately after `search`
              insert_before – insert `replacement` text immediately before `search`
              delete_lines  – delete lines `line_start`..`line_end` (1-indexed, inclusive)
              append        – append `replacement` to the end of the file
            """
            p = _safe_path(args["path"])
            if not p.exists():
                raise ToolExecutionError(f"File not found: {p}")

            size = p.stat().st_size
            if size > _EDIT_MAX_FILE_SIZE:
                raise ToolExecutionError(
                    f"File is too large to edit safely ({size:,} bytes; cap is {_EDIT_MAX_FILE_SIZE:,})."
                )

            text = p.read_text(errors="replace")
            operation = args["operation"]

            # ---- replace ----
            if operation == "replace":
                search = args.get("search", "")
                replacement = args.get("replacement", "")
                replace_all = args.get("replace_all", False)
                if not search:
                    raise ToolExecutionError("Parameter 'search' is required for replace.")
                if replace_all:
                    count = text.count(search)
                    if count == 0:
                        raise ToolExecutionError("Search text not found in file.")
                    text = text.replace(search, replacement)
                    summary = f"Replaced {count} occurrence(s)."
                else:
                    idx = text.find(search)
                    if idx == -1:
                        raise ToolExecutionError("Search text not found in file.")
                    text = text[:idx] + replacement + text[idx + len(search):]
                    summary = "Replaced 1 occurrence."

            # ---- insert_after ----
            elif operation == "insert_after":
                search = args.get("search", "")
                replacement = args.get("replacement", "")
                if not search:
                    raise ToolExecutionError("Parameter 'search' is required for insert_after.")
                idx = text.find(search)
                if idx == -1:
                    raise ToolExecutionError("Search text not found in file.")
                insert_point = idx + len(search)
                text = text[:insert_point] + replacement + text[insert_point:]
                line_num = text[:insert_point].count("\n") + 1
                summary = f"Inserted {len(replacement)} chars after line {line_num}."

            # ---- insert_before ----
            elif operation == "insert_before":
                search = args.get("search", "")
                replacement = args.get("replacement", "")
                if not search:
                    raise ToolExecutionError("Parameter 'search' is required for insert_before.")
                idx = text.find(search)
                if idx == -1:
                    raise ToolExecutionError("Search text not found in file.")
                text = text[:idx] + replacement + text[idx:]
                line_num = text[:idx].count("\n") + 1
                summary = f"Inserted {len(replacement)} chars before line {line_num}."

            # ---- delete_lines ----
            elif operation == "delete_lines":
                line_start = int(args.get("line_start", 0))
                line_end = int(args.get("line_end", line_start))
                if line_start < 1:
                    raise ToolExecutionError("line_start must be >= 1.")
                if line_end < line_start:
                    raise ToolExecutionError("line_end must be >= line_start.")
                lines = text.splitlines(keepends=True)
                if line_start > len(lines):
                    raise ToolExecutionError(
                        f"line_start ({line_start}) exceeds file line count ({len(lines)})."
                    )
                actual_end = min(line_end, len(lines))
                deleted = "".join(lines[line_start - 1: actual_end])
                new_lines = lines[: line_start - 1] + lines[actual_end:]
                text = "".join(new_lines)
                summary = f"Deleted lines {line_start}-{actual_end} ({len(deleted.splitlines())} line(s))."

            # ---- append ----
            elif operation == "append":
                replacement = args.get("replacement", "")
                if text and not text.endswith("\n"):
                    text += "\n"
                text += replacement
                summary = f"Appended {len(replacement)} chars."

            else:
                raise ToolExecutionError(
                    f"Unknown operation '{operation}'. "
                    "Use: replace, insert_after, insert_before, delete_lines, append."
                )

            # --- confirmation (if enabled) ---
            if confirm_before_write:
                if not confirm_fn(f"Edit file {p} ({operation})?"):
                    raise ToolExecutionError("User declined the edit.")

            p.write_text(text)

            # Build a helpful preview of the changed region
            preview = ""
            if "line_num" in dir():
                pass
            elif operation == "delete_lines":
                # Show lines around the deletion point
                preview = _preview_lines(text, line_start, radius=3)
            elif operation in ("replace", "insert_after", "insert_before"):
                search_key = args.get("replacement", "") or args.get("search", "")
                ln = _find_line_number(text, search_key) if search_key else -1
                if ln > 0:
                    preview = _preview_lines(text, ln, radius=3)
            elif operation == "append":
                total_lines = text.count("\n") + 1
                preview = _preview_lines(text, total_lines, radius=3)

            if preview:
                return f"{summary}\n\nPreview (lines near edit):\n{preview}"
            return summary

        tools.append(
            (
                ToolSpec(
                    name="edit_file",
                    description=(
                        "Edit an existing file in place with targeted operations. "
                        "Supports: replace (find & replace text), insert_after, insert_before, "
                        "delete_lines (by line number range), append. "
                        "Does NOT rewrite the whole file — only the targeted region changes. "
                        "Returns a summary and a preview of the edited region."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file to edit.",
                            },
                            "operation": {
                                "type": "string",
                                "enum": ["replace", "insert_after", "insert_before", "delete_lines", "append"],
                                "description": "Type of edit to perform.",
                            },
                            "search": {
                                "type": "string",
                                "description": "Text to find (required for replace, insert_after, insert_before).",
                            },
                            "replacement": {
                                "type": "string",
                                "description": "Replacement or insertion text (required for replace, insert_after, insert_before, append).",
                            },
                            "replace_all": {
                                "type": "boolean",
                                "description": "If true, replace ALL occurrences (replace operation only). Default: false.",
                            },
                            "line_start": {
                                "type": "integer",
                                "description": "First line number to delete (1-indexed). Required for delete_lines.",
                            },
                            "line_end": {
                                "type": "integer",
                                "description": "Last line number to delete (1-indexed, inclusive). Defaults to line_start.",
                            },
                        },
                        "required": ["path", "operation"],
                    },
                ),
                edit_file,
            )
        )

        def list_directory(args: Dict[str, Any]) -> str:
            p = _safe_path(args.get("path", "."))
            if not p.exists():
                raise ToolExecutionError(f"Path not found: {p}")
            if not p.is_dir():
                raise ToolExecutionError(f"{p} is not a directory")
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            lines = []
            for e in entries[:500]:
                kind = "dir " if e.is_dir() else "file"
                size = "" if e.is_dir() else f" ({e.stat().st_size}b)"
                lines.append(f"[{kind}] {e.name}{size}")
            return "\n".join(lines) if lines else "(empty directory)"

        tools.append(
            (
                ToolSpec(
                    name="list_directory",
                    description="List files and subdirectories at a given path (defaults to current directory).",
                    input_schema={
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "Directory path"}},
                    },
                ),
                list_directory,
            )
        )

    if enable_shell:
        def run_shell(args: Dict[str, Any]) -> str:
            command = args["command"]
            # --- allowlist check ------------------------------------------------
            if not _command_allowed(command, allowed_shell_commands):
                allowed_str = ", ".join(allowed_shell_commands) if allowed_shell_commands else "(none)"
                raise ToolExecutionError(
                    f"Command not in allowlist. Allowed: {allowed_str}"
                )
            # --- confirmation (if enabled) -------------------------------------
            if confirm_before_shell:
                if not confirm_fn(f"Run shell command?\n  $ {command}"):
                    raise ToolExecutionError("User declined to run this command.")
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=args.get("timeout_seconds", 30),
                    cwd=os.getcwd(),
                )
            except subprocess.TimeoutExpired:
                raise ToolExecutionError("Command timed out.")
            out = proc.stdout[-8000:]
            err = proc.stderr[-4000:]
            return f"exit_code={proc.returncode}\nstdout:\n{out}\nstderr:\n{err}"

        tools.append(
            (
                ToolSpec(
                    name="run_shell_command",
                    description="Execute a shell command on the local machine and return its output. Use with caution.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "timeout_seconds": {"type": "integer"},
                        },
                        "required": ["command"],
                    },
                ),
                run_shell,
            )
        )

    if enable_http:
        def http_get(args: Dict[str, Any]) -> str:
            import requests

            url = args["url"]
            try:
                resp = requests.get(url, timeout=15, headers={"User-Agent": "ai-cli-assistant/0.1"})
            except Exception as e:  # noqa: BLE001
                raise ToolExecutionError(f"Request failed: {e}")
            text = resp.text
            max_chars = 20_000
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n...[truncated, {len(text) - max_chars} more chars]"
            return f"status={resp.status_code}\n\n{text}"

        tools.append(
            (
                ToolSpec(
                    name="http_get",
                    description="Fetch a URL over HTTP GET and return the response body as text.",
                    input_schema={
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                ),
                http_get,
            )
        )

    def calculator(args: Dict[str, Any]) -> str:
        import ast
        import operator as op

        ops = {
            ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
            ast.Pow: op.pow, ast.Mod: op.mod, ast.USub: op.neg, ast.FloorDiv: op.floordiv,
        }

        def ev(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in ops:
                return ops[type(node.op)](ev(node.left), ev(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
                return ops[type(node.op)](ev(node.operand))
            raise ToolExecutionError("Unsupported expression.")

        try:
            tree = ast.parse(args["expression"], mode="eval")
            return str(ev(tree.body))
        except ToolExecutionError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ToolExecutionError(f"Could not evaluate expression: {e}")

    tools.append(
        (
            ToolSpec(
                name="calculator",
                description="Evaluate a basic arithmetic expression (+, -, *, /, //, %, **). Use for precise math.",
                input_schema={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            ),
            calculator,
        )
    )

    return tools
