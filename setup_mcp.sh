#!/usr/bin/env bash
# Install Node.js LTS and uv (uvx), then pre-cache MCP server packages.
set -euo pipefail

echo "=== 1. Install Node.js LTS (for npx-based MCP servers) ==="
if command -v node &>/dev/null && command -v npx &>/dev/null; then
  echo "Node.js already installed: $(node --version)"
else
  echo "Installing Node.js LTS via NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
  apt-get install -y nodejs
  echo "Installed Node.js: $(node --version)"
  echo "Installed npm: $(npm --version)"
fi

echo ""
echo "=== 2. Install uv / uvx (for Python-based MCP servers) ==="
if command -v uvx &>/dev/null; then
  echo "uv/uvx already installed: $(uvx --version 2>/dev/null || uv --version)"
else
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  # Persist to PATH for future shells
  if ! grep -q '.local/bin' "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  fi
  echo "Installed uv: $(uv --version)"
fi

echo ""
echo "=== 3. Pre-cache npx-based MCP servers ==="
NPX_SERVERS=(
  "@modelcontextprotocol/server-filesystem"
  "@modelcontextprotocol/server-memory"
  "@modelcontextprotocol/server-sequential-thinking"
  "@modelcontextprotocol/server-puppeteer"
  "@modelcontextprotocol/server-everything"
  "@modelcontextprotocol/server-postgres"
  "@modelcontextprotocol/server-github"
  "@modelcontextprotocol/server-brave-search"
  "@modelcontextprotocol/server-google-drive"
  "@modelcontextprotocol/server-slack"
  "@modelcontextprotocol/server-google-maps"
  "@modelcontextprotocol/server-everart"
)
for pkg in "${NPX_SERVERS[@]}"; do
  echo "  caching $pkg ..."
  npx -y "$pkg" --help &>/dev/null || npx -y "$pkg" --version &>/dev/null || true
done

echo ""
echo "=== 4. Pre-cache uvx-based MCP servers ==="
UVX_SERVERS=(
  "mcp-server-fetch"
  "mcp-server-git"
  "mcp-server-time"
  "mcp-server-sqlite"
)
for pkg in "${UVX_SERVERS[@]}"; do
  echo "  caching $pkg ..."
  uvx "$pkg" --help &>/dev/null || true
done

echo ""
echo "=== Done! ==="
echo "Node.js: $(node --version 2>/dev/null || echo 'not found')"
echo "npx: $(npx --version 2>/dev/null || echo 'not found')"
echo "uv: $(uv --version 2>/dev/null || echo 'not found')"
echo "uvx: $(uvx --version 2>/dev/null || echo 'not found')"
