"""
A curated catalog of known MCP servers and a manager for adding/removing
them from ~/.ai-cli/mcp_servers.json.

Usage from the CLI:
    ai mcp list              show all available servers in the catalog
    ai mcp installed         show servers currently in your config
    ai mcp add <name>        add a server (interactive -- prompts for paths/keys)
    ai mcp add-custom        add a custom server not in the catalog
    ai mcp remove <name>     remove a server from your config
    ai mcp install <name>    pre-download the server package (npx/uvx cache)
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .config import MCP_SERVERS_PATH, load_mcp_servers

# -- catalog ------------------------------------------------------------------

NPX = "npx"
UVX = "uvx"


@dataclass
class MCPCatalogEntry:
    name: str
    description: str
    command: str  # "npx" or "uvx"
    package: str  # npm package name or pip package name
    needs_path: bool = False  # requires a path/URL argument after the package
    path_label: str = ""  # what to ask the user for (e.g. "Allowed directory")
    path_placeholder: str = ""  # default placeholder
    needs_api_key: bool = False
    env_keys: Dict[str, str] = field(default_factory=dict)  # env var -> label for prompt
    extra_args: List[str] = field(default_factory=list)  # fixed args before the path


CATALOG: Dict[str, MCPCatalogEntry] = {
    # -- no API key required (just works) --
    "filesystem": MCPCatalogEntry(
        name="filesystem",
        description="Secure file read/write with configurable access controls",
        command=NPX,
        package="@modelcontextprotocol/server-filesystem",
        needs_path=True,
        path_label="Allowed directory path",
        path_placeholder="/home/user/projects",
    ),
    "fetch": MCPCatalogEntry(
        name="fetch",
        description="Web content fetching and conversion for LLM usage",
        command=UVX,
        package="mcp-server-fetch",
    ),
    "git": MCPCatalogEntry(
        name="git",
        description="Read, search, and manipulate Git repositories",
        command=UVX,
        package="mcp-server-git",
        needs_path=True,
        path_label="Path to Git repository",
        path_placeholder="/home/user/my-repo",
        extra_args=["--repository"],
    ),
    "memory": MCPCatalogEntry(
        name="memory",
        description="Knowledge graph-based persistent memory system",
        command=NPX,
        package="@modelcontextprotocol/server-memory",
    ),
    "sequential-thinking": MCPCatalogEntry(
        name="sequential-thinking",
        description="Dynamic and reflective problem-solving through thought sequences",
        command=NPX,
        package="@modelcontextprotocol/server-sequential-thinking",
    ),
    "time": MCPCatalogEntry(
        name="time",
        description="Time and timezone conversion capabilities",
        command=UVX,
        package="mcp-server-time",
    ),
    "puppeteer": MCPCatalogEntry(
        name="puppeteer",
        description="Browser automation and web scraping (downloads Chromium)",
        command=NPX,
        package="@modelcontextprotocol/server-puppeteer",
    ),
    "everything": MCPCatalogEntry(
        name="everything",
        description="Reference/test server with prompts, resources, and tools",
        command=NPX,
        package="@modelcontextprotocol/server-everything",
    ),
    "sqlite": MCPCatalogEntry(
        name="sqlite",
        description="SQLite database interaction and business intelligence",
        command=UVX,
        package="mcp-server-sqlite",
        needs_path=True,
        path_label="Path to SQLite database file",
        path_placeholder="/home/user/data.db",
        extra_args=["--db-path"],
    ),
    "postgres": MCPCatalogEntry(
        name="postgres",
        description="PostgreSQL read-only database access with schema inspection",
        command=NPX,
        package="@modelcontextprotocol/server-postgres",
        needs_path=True,
        path_label="PostgreSQL connection string",
        path_placeholder="postgresql://user:password@localhost:5432/dbname",
    ),
    # -- API key required --
    "github": MCPCatalogEntry(
        name="github",
        description="GitHub repo management, file operations, and API integration",
        command=NPX,
        package="@modelcontextprotocol/server-github",
        needs_api_key=True,
        env_keys={"GITHUB_PERSONAL_ACCESS_TOKEN": "GitHub personal access token (ghp_...)"},
    ),
    "brave-search": MCPCatalogEntry(
        name="brave-search",
        description="Web and local search using Brave's Search API",
        command=NPX,
        package="@modelcontextprotocol/server-brave-search",
        needs_api_key=True,
        env_keys={"BRAVE_API_KEY": "Brave Search API key"},
    ),
    "google-drive": MCPCatalogEntry(
        name="google-drive",
        description="File access and search for Google Drive",
        command=NPX,
        package="@modelcontextprotocol/server-google-drive",
        needs_api_key=True,
        env_keys={
            "GOOGLE_CLIENT_ID": "Google OAuth client ID",
            "GOOGLE_CLIENT_SECRET": "Google OAuth client secret",
        },
    ),
    "slack": MCPCatalogEntry(
        name="slack",
        description="Slack channel management and messaging",
        command=NPX,
        package="@modelcontextprotocol/server-slack",
        needs_api_key=True,
        env_keys={
            "SLACK_BOT_TOKEN": "Slack bot token (xoxb-...)",
            "SLACK_TEAM_ID": "Slack team ID",
        },
    ),
    "google-maps": MCPCatalogEntry(
        name="google-maps",
        description="Google Maps location services, directions, and places",
        command=NPX,
        package="@modelcontextprotocol/server-google-maps",
        needs_api_key=True,
        env_keys={"GOOGLE_MAPS_API_KEY": "Google Maps API key"},
    ),
    "everart": MCPCatalogEntry(
        name="everart",
        description="AI image generation using various models",
        command=NPX,
        package="@modelcontextprotocol/server-everart",
        needs_api_key=True,
        env_keys={"EVERART_API_KEY": "EverArt API key"},
    ),
}


# -- helpers ------------------------------------------------------------------


def _read_mcp_json() -> Dict[str, Any]:
    if not MCP_SERVERS_PATH.exists():
        return {"mcpServers": {}}
    with open(MCP_SERVERS_PATH, "r") as f:
        return json.load(f)


def _write_mcp_json(data: Dict[str, Any]) -> None:
    MCP_SERVERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MCP_SERVERS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _build_server_config(entry: MCPCatalogEntry, path_value: str, env_values: Dict[str, str]) -> Dict[str, Any]:
    args: List[str] = []
    if entry.command == NPX:
        args.extend(["-y", entry.package])
    else:
        args.append(entry.package)
    args.extend(entry.extra_args)
    if entry.needs_path and path_value:
        args.append(path_value)

    config: Dict[str, Any] = {"command": entry.command, "args": args}
    if env_values:
        config["env"] = {k: v for k, v in env_values.items() if v}
    return config


def _install_package(entry: MCPCatalogEntry, console: Console) -> bool:
    """Pre-download the package so the first real run is instant."""
    console.print(f"[dim]Pre-caching {entry.package} ...[/dim]")
    cmd: List[str] = [entry.command]
    if entry.command == NPX:
        cmd.append("-y")
    cmd.append(entry.package)
    try:
        subprocess.run(
            cmd + ["--help"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Many MCP servers don't support --help and exit non-zero, but the
        # package still got downloaded by npx/uvx. That's fine.
        return True
    except FileNotFoundError:
        console.print(f"[red]'{entry.command}' not found on PATH.[/red]")
        if entry.command == NPX:
            console.print("[dim]Install Node.js: https://nodejs.org/[/dim]")
        else:
            console.print("[dim]Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh[/dim]")
        return False
    except subprocess.TimeoutExpired:
        console.print("[yellow](timed out but package may still be cached)[/yellow]")
        return True
    except Exception:  # noqa: BLE001
        return True


# -- public commands -----------------------------------------------------------


def cmd_list(console: Console) -> int:
    """Show all servers in the catalog."""
    installed = {s.name for s in load_mcp_servers()}

    table = Table(title="Available MCP Servers", show_header=True, header_style="bold cyan")
    table.add_column("", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Via", justify="center")
    table.add_column("API Key", justify="center")

    for entry in CATALOG.values():
        marker = "[green]✓[/green]" if entry.name in installed else "[dim]○[/dim]"
        key_badge = "[yellow]required[/yellow]" if entry.needs_api_key else "[green]none[/green]"
        table.add_row(marker, entry.name, entry.description, entry.command, key_badge)

    console.print(table)
    console.print(
        "\n[dim]✓ = installed    ○ = available    Use `ai mcp add <name>` to install one.[/dim]"
    )
    return 0


def cmd_installed(console: Console) -> int:
    """Show servers currently in the config."""
    servers = load_mcp_servers()
    if not servers:
        console.print("[dim]No MCP servers configured. Run `ai mcp list` to see options.[/dim]")
        return 0

    table = Table(title="Installed MCP Servers", show_header=True, header_style="bold green")
    table.add_column("Name", style="bold")
    table.add_column("Command")
    table.add_column("Args")
    table.add_column("Env Keys", justify="center")

    for s in servers:
        args_str = " ".join(s.args) if s.args else "[dim](none)[/dim]"
        env_keys = ", ".join(s.env.keys()) if s.env else "[dim]none[/dim]"
        table.add_row(s.name, s.command, args_str, env_keys)

    console.print(table)
    return 0


def cmd_add(console: Console, name: str) -> int:
    """Add a server from the catalog to the config."""
    entry = CATALOG.get(name)
    if not entry:
        console.print(f"[red]Unknown server '{name}'.[/red] Run `ai mcp list` to see options.")
        return 1

    data = _read_mcp_json()
    existing = (data.get("mcpServers") or {}).get(name)
    if existing:
        if not Confirm.ask(f"'{name}' is already configured. Overwrite?", default=False):
            console.print("[yellow]Cancelled.[/yellow]")
            return 0

    console.print(f"\n[bold cyan]Adding MCP server: {name}[/bold cyan]")
    console.print(f"[dim]{entry.description}[/dim]\n")

    # Collect path if needed
    path_value = ""
    if entry.needs_path:
        path_value = Prompt.ask(entry.path_label, default=entry.path_placeholder)

    # Collect env vars if needed
    env_values: Dict[str, str] = {}
    if entry.needs_api_key or entry.env_keys:
        console.print()
        for env_key, label in entry.env_keys.items():
            val = Prompt.ask(label, password=True, default="")
            if val:
                env_values[env_key] = val
            else:
                console.print(f"[yellow]  (skipped {env_key} -- you can add it later)[/yellow]")

    # Build and save
    server_config = _build_server_config(entry, path_value, env_values)
    servers = data.setdefault("mcpServers", {})
    servers[name] = server_config
    _write_mcp_json(data)

    console.print(f"\n[green]✓ Added '{name}' to {MCP_SERVERS_PATH}[/green]")

    # Offer to pre-download
    if Confirm.ask("\nPre-download the package now? (makes first run faster)", default=True):
        _install_package(entry, console)

    console.print(f"\n[dim]The server will connect next time you run `ai`.[/dim]")
    return 0


def cmd_remove(console: Console, name: str) -> int:
    """Remove a server from the config."""
    data = _read_mcp_json()
    servers = data.get("mcpServers") or {}
    if name not in servers:
        console.print(f"[red]'{name}' is not in your config.[/red]")
        return 1

    if not Confirm.ask(f"Remove '{name}' from your MCP config?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return 0

    del servers[name]
    data["mcpServers"] = servers
    _write_mcp_json(data)
    console.print(f"[green]✓ Removed '{name}' from {MCP_SERVERS_PATH}[/green]")
    return 0


def cmd_install(console: Console, name: str) -> int:
    """Pre-download a server package without adding it to config."""
    entry = CATALOG.get(name)
    if not entry:
        console.print(f"[red]Unknown server '{name}'.[/red] Run `ai mcp list` to see options.")
        return 1

    console.print(f"[bold]Pre-caching {entry.package} via {entry.command} ...[/bold]")
    success = _install_package(entry, console)
    if success:
        console.print(f"[green]✓ Cached {entry.package}[/green]")
        return 0
    return 1


def cmd_add_custom(console: Console) -> int:
    """Interactively add a custom MCP server not in the catalog."""
    console.print("[bold cyan]Add custom MCP server[/bold cyan]\n")

    name = Prompt.ask("Server name (used as a namespace, e.g. 'my-tool')", default="")
    if not name:
        console.print("[red]A name is required.[/red]")
        return 1

    command = Prompt.ask("Command to run", choices=["npx", "uvx", "python", "node"], default="npx")

    args_raw = Prompt.ask("Arguments (space-separated, e.g. -y @some/mcp-server /path)", default="")
    args = args_raw.split() if args_raw else []

    env_keys_raw = Prompt.ask("Environment variables (KEY=value pairs, comma-separated, or blank)", default="")
    env: Dict[str, str] = {}
    if env_keys_raw:
        for pair in env_keys_raw.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                env[k.strip()] = v.strip()

    data = _read_mcp_json()
    servers = data.setdefault("mcpServers", {})
    servers[name] = {"command": command, "args": args}
    if env:
        servers[name]["env"] = env
    _write_mcp_json(data)

    console.print(f"\n[green]✓ Added custom server '{name}' to {MCP_SERVERS_PATH}[/green]")
    return 0


# -- entrypoint ---------------------------------------------------------------

MCP_USAGE = (
    "Usage:\n"
    "  ai mcp list               show all available MCP servers (catalog)\n"
    "  ai mcp installed           show servers in your config\n"
    "  ai mcp add <name>          add a server from the catalog (interactive)\n"
    "  ai mcp add-custom          add a custom server not in the catalog\n"
    "  ai mcp remove <name>       remove a server from your config\n"
    "  ai mcp install <name>      pre-download a server package"
)


def handle_mcp(console: Console, sub_argv: List[str]) -> int:
    if not sub_argv:
        console.print(MCP_USAGE)
        return 0

    action = sub_argv[0]

    if action in ("-h", "--help"):
        console.print(MCP_USAGE)
        return 0

    if action == "list":
        return cmd_list(console)

    if action == "installed":
        return cmd_installed(console)

    if action == "add":
        if len(sub_argv) < 2:
            console.print("[red]Usage: ai mcp add <name>[/red]\n")
            return cmd_list(console)
        return cmd_add(console, sub_argv[1])

    if action == "add-custom":
        return cmd_add_custom(console)

    if action == "remove":
        if len(sub_argv) < 2:
            console.print("[red]Usage: ai mcp remove <name>[/red]")
            return 1
        return cmd_remove(console, sub_argv[1])

    if action == "install":
        if len(sub_argv) < 2:
            console.print("[red]Usage: ai mcp install <name>[/red]")
            return 1
        return cmd_install(console, sub_argv[1])

    console.print(f"[red]Unknown action '{action}'.[/red]\n{MCP_USAGE}")
    return 0
