#!/usr/bin/env bash
# setup.sh -- one script to get ai-cli-assistant running anywhere.
#
# Detects where it's running (Railway, a container, a Linux VPS with
# apt/dnf/apk/pacman, or macOS with brew) and adapts:
#   - installs Python 3 + pip if it can
#   - creates a virtualenv and installs the project into it
#   - runs the interactive setup wizard (model/provider/bots) if there's a
#     real terminal attached, otherwise prints the env-var equivalent
#   - offers to install a persistent background service (systemd on Linux,
#     launchd on macOS) so bots survive reboots/logouts -- skipped
#     automatically on Railway/containers, which manage the process for you
#
# Usage:
#   ./setup.sh                interactive, asks before anything risky
#   ./setup.sh --yes          assume yes to every prompt (unattended VPS provisioning)
#   ./setup.sh --no-venv      install into the system/current Python instead of a venv
#   ./setup.sh --no-service   skip the systemd/launchd offer
#   ./setup.sh --no-wizard    skip the interactive AI setup wizard step
set -euo pipefail

# -- flags --------------------------------------------------------------------

ASSUME_YES=0
USE_VENV=1
OFFER_SERVICE=1
RUN_WIZARD=1

for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --no-venv) USE_VENV=0 ;;
    --no-service) OFFER_SERVICE=0 ;;
    --no-wizard) RUN_WIZARD=0 ;;
    -h|--help)
      awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
      exit 0
      ;;
    *)
      echo "Unknown flag: $arg (see --help)"
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# -- output helpers -------------------------------------------------------------

c_reset='\033[0m'; c_bold='\033[1m'; c_cyan='\033[36m'; c_green='\033[32m'; c_yellow='\033[33m'; c_red='\033[31m'
info()  { printf "${c_cyan}==>${c_reset} %b\n" "$1"; }
ok()    { printf "${c_green}  ok${c_reset} %b\n" "$1"; }
warn()  { printf "${c_yellow}  ! ${c_reset} %b\n" "$1"; }
err()   { printf "${c_red}  x ${c_reset} %b\n" "$1"; }
ask_yes_no() {
  # ask_yes_no "question" default(y/n) -> returns 0 for yes
  if [ "$ASSUME_YES" = "1" ]; then return 0; fi
  local prompt="$1" default="${2:-n}" reply
  if [ ! -t 0 ]; then return 1; fi  # no terminal attached -- default to no
  if [ "$default" = "y" ]; then
    read -r -p "$prompt [Y/n] " reply || true
    [ -z "$reply" ] && return 0
  else
    read -r -p "$prompt [y/N] " reply || true
    [ -z "$reply" ] && return 1
  fi
  case "$reply" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

printf "${c_bold}${c_cyan}\n"
printf "  ai-cli-assistant setup\n"
printf "${c_reset}\n"

# -- 1. detect platform -----------------------------------------------------

PLATFORM="vps"
PKG_MANAGER=""
OS_NAME="$(uname -s)"

if [ -n "${RAILWAY_ENVIRONMENT:-}" ] || [ -n "${RAILWAY_PROJECT_ID:-}" ]; then
  PLATFORM="railway"
elif [ -f /.dockerenv ] || [ -n "${container:-}" ]; then
  PLATFORM="container"
elif [ "$OS_NAME" = "Darwin" ]; then
  PLATFORM="macos"
elif [ "$OS_NAME" = "Linux" ]; then
  PLATFORM="vps"
  if command -v apt-get >/dev/null 2>&1; then PKG_MANAGER="apt"
  elif command -v dnf >/dev/null 2>&1; then PKG_MANAGER="dnf"
  elif command -v yum >/dev/null 2>&1; then PKG_MANAGER="yum"
  elif command -v apk >/dev/null 2>&1; then PKG_MANAGER="apk"
  elif command -v pacman >/dev/null 2>&1; then PKG_MANAGER="pacman"
  fi
fi

info "Detected platform: ${c_bold}${PLATFORM}${c_reset}${PKG_MANAGER:+ (package manager: $PKG_MANAGER)}"

if [ "$PLATFORM" = "railway" ] || [ "$PLATFORM" = "container" ]; then
  warn "Running inside a managed container -- skipping system package installs and the systemd/launchd service (the platform already keeps your process running)."
  OFFER_SERVICE=0
fi

# -- 2. python3 + pip ---------------------------------------------------------

info "Checking for Python 3.9+..."
PYTHON_BIN=""
for cand in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
    major="${ver%%.*}"; minor="${ver##*.}"
    if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then PYTHON_BIN="$cand"; break; fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  warn "No suitable Python 3.9+ found."
  if ask_yes_no "Attempt to install Python 3 now?" y; then
    case "$PKG_MANAGER" in
      apt)   sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip ;;
      dnf)   sudo dnf install -y python3 python3-pip ;;
      yum)   sudo yum install -y python3 python3-pip ;;
      apk)   sudo apk add --no-cache python3 py3-pip ;;
      pacman) sudo pacman -Sy --noconfirm python python-pip ;;
      *)
        if [ "$PLATFORM" = "macos" ] && command -v brew >/dev/null 2>&1; then
          brew install python3
        else
          err "Don't know how to install Python on this system. Install Python 3.9+ manually, then re-run this script."
          exit 1
        fi
        ;;
    esac
    PYTHON_BIN="python3"
  else
    err "Python 3.9+ is required. Install it and re-run."
    exit 1
  fi
fi
ok "using $($PYTHON_BIN --version)"

# -- 3. virtualenv + install --------------------------------------------------

if [ "$USE_VENV" = "1" ]; then
  if [ ! -d ".venv" ]; then
    info "Creating virtual environment at ./.venv ..."
    "$PYTHON_BIN" -m venv .venv || {
      warn "venv module unavailable -- attempting to install it"
      case "$PKG_MANAGER" in
        apt) sudo apt-get install -y python3-venv ;;
      esac
      "$PYTHON_BIN" -m venv .venv
    }
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  PYTHON_BIN="python"
  ok "virtualenv ready (./.venv) -- activate later with: source .venv/bin/activate"
else
  warn "Skipping virtualenv (--no-venv) -- installing into $PYTHON_BIN directly."
fi

info "Installing Python dependencies (this pulls in the Discord bot library too -- it's not tiny, but you said resources aren't a concern)..."
"$PYTHON_BIN" -m pip install --upgrade pip --quiet
"$PYTHON_BIN" -m pip install -r requirements.txt --quiet
"$PYTHON_BIN" -m pip install -e . --quiet
ok "dependencies installed, 'ai' command available"

AI_BIN="ai"
if [ "$USE_VENV" = "1" ]; then
  AI_BIN="$SCRIPT_DIR/.venv/bin/ai"
fi

# -- 4. interactive setup wizard ------------------------------------------------

if [ "$RUN_WIZARD" = "1" ]; then
  if [ -t 0 ] && [ -t 1 ]; then
    info "Launching the interactive setup wizard (provider/model/tools/bots)..."
    "$AI_BIN" --setup || warn "Wizard exited early -- you can re-run it any time with 'ai --setup'."
  else
    warn "No interactive terminal detected -- skipping the wizard."
    echo "    Configure via environment variables instead -- see .env.example, or run:"
    echo "      $AI_BIN --setup"
    echo "    later from a real terminal (e.g. 'railway shell' on Railway, or SSH on a VPS)."
  fi
else
  warn "Skipping the setup wizard (--no-wizard)."
fi

# -- 5. persistent background service (VPS/macOS only) -----------------------

if [ "$OFFER_SERVICE" = "1" ]; then
  if [ "$PLATFORM" = "vps" ] && command -v systemctl >/dev/null 2>&1; then
    if ask_yes_no "Install a systemd --user service so bots keep running after you log out?" y; then
      SERVICE_DIR="$HOME/.config/systemd/user"
      mkdir -p "$SERVICE_DIR"
      cat > "$SERVICE_DIR/ai-cli-bots.service" <<SERVICEEOF
[Unit]
Description=ai-cli-assistant bots (Telegram/Discord)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$AI_BIN serve
Restart=on-failure
RestartSec=5
Environment=AI_CLI_NONINTERACTIVE=1

[Install]
WantedBy=default.target
SERVICEEOF
      systemctl --user daemon-reload
      systemctl --user enable --now ai-cli-bots.service
      # Let the user service keep running after SSH logout / reboot.
      if command -v loginctl >/dev/null 2>&1; then
        loginctl enable-linger "$(whoami)" 2>/dev/null || warn "Couldn't enable lingering automatically -- run: sudo loginctl enable-linger $(whoami)"
      fi
      ok "installed and started. Check status with: systemctl --user status ai-cli-bots"
      echo "    Logs: journalctl --user -u ai-cli-bots -f"
    fi
  elif [ "$PLATFORM" = "macos" ]; then
    if ask_yes_no "Install a launchd agent so bots keep running in the background?" y; then
      PLIST_DIR="$HOME/Library/LaunchAgents"
      mkdir -p "$PLIST_DIR"
      PLIST_PATH="$PLIST_DIR/com.aicli.bots.plist"
      cat > "$PLIST_PATH" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.aicli.bots</string>
  <key>ProgramArguments</key>
  <array>
    <string>$AI_BIN</string>
    <string>serve</string>
  </array>
  <key>WorkingDirectory</key><string>$SCRIPT_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>AI_CLI_NONINTERACTIVE</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$SCRIPT_DIR/.ai-cli-bots.log</string>
  <key>StandardErrorPath</key><string>$SCRIPT_DIR/.ai-cli-bots.log</string>
</dict>
</plist>
PLISTEOF
      launchctl unload "$PLIST_PATH" 2>/dev/null || true
      launchctl load "$PLIST_PATH"
      ok "installed and started. Logs: tail -f $SCRIPT_DIR/.ai-cli-bots.log"
      echo "    Stop with: launchctl unload $PLIST_PATH"
    fi
  fi
fi

# -- 6. summary ------------------------------------------------------------------

printf "\n${c_bold}${c_green}Setup complete.${c_reset}\n\n"
echo "Next steps:"
[ "$USE_VENV" = "1" ] && echo "  source .venv/bin/activate   # each new shell"
echo "  ai                          # start the interactive REPL"
echo "  ai bots status               # see which bots are configured"
echo "  ai bots run all              # run bots in the foreground"
echo "  ai serve                     # production entrypoint (used by Docker/Railway/the service above)"
echo
case "$PLATFORM" in
  railway)
    echo "On Railway: set env vars in the service's Variables tab (see .env.example), then deploy --"
    echo "the Dockerfile + railway.json in this repo already point at 'ai serve'."
    ;;
  container)
    echo "Inside a container: set the env vars in .env.example on the container, then run 'ai serve'."
    ;;
esac
