"""
Built-in tools. Each tool is a (ToolSpec, handler) pair. Handlers take a
dict of arguments and return a plain string result. Handlers raise
ToolExecutionError on failure; the caller turns that into a tool_result
with is_error=True so the model can see and react to it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from ..providers.base import ToolSpec


class ToolExecutionError(RuntimeError):
    pass


ToolHandler = Callable[[Dict[str, Any]], str]


def _safe_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def make_builtin_tools(
    enable_filesystem: bool,
    enable_shell: bool,
    enable_http: bool,
    confirm_before_write: bool,
    confirm_before_shell: bool,
    confirm_fn: Callable[[str], bool],
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
