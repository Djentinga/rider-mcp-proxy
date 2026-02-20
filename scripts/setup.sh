#!/bin/bash
# Auto-install prerequisites and configure Serena C# LSP.
# Called by SessionStart hook. Idempotent — skips what's already installed.
# Best-effort: individual steps may fail without blocking the session.

log() { echo "[mcp-setup] $*" >&2; }

# --- uv / uvx ---
if ! command -v uvx &>/dev/null; then
    log "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || log "uv install failed"
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- .NET 10 ---
if ! command -v dotnet &>/dev/null || ! dotnet --list-sdks 2>/dev/null | grep -q "^10\."; then
    log "Installing .NET 10 SDK..."
    curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0 || log ".NET install failed"
    export PATH="$HOME/.dotnet:$PATH"
fi

# --- Patch Serena: skip csproj BFS when .sln/.slnx found ---
target=$(find "$HOME/.cache/uv/archive-v0" -path "*/solidlsp/language_servers/csharp_language_server.py" 2>/dev/null | head -1)

if [ -n "$target" ] && ! grep -q "# \[djentinga-mcp\] skip csproj BFS" "$target" 2>/dev/null; then
    log "Patching Serena: skip csproj BFS when solution found..."
    python3 - "$target" <<'PYEOF' || log "Serena patch failed"
import sys

path = sys.argv[1]
with open(path) as f:
    content = f.read()

old = '''            log.debug(f"Opened solution file: {solution_file}")

        # Find and open project files'''

new = '''            log.debug(f"Opened solution file: {solution_file}")
            return  # [djentinga-mcp] skip csproj BFS — solution already provides project info

        # Find and open project files'''

if old in content:
    content = content.replace(old, new)
    with open(path, 'w') as f:
        f.write(content)
PYEOF
fi

exit 0
