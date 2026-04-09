#!/bin/bash
# Auto-detect JetBrains Rider and proxy MCP via streamable-http.
# Supports both Remote Dev (Linux-native) and Windows-side Rider on WSL2.

set -euo pipefail

MODE=""  # "linux" or "windows"

# --- Ensure WSL2 mirrored networking for localhost forwarding ---
ensure_wsl_networking() {
    # Only applies inside WSL2
    grep -qi microsoft /proc/version 2>/dev/null || return 0

    local user_profile wslconfig wsl_dir
    user_profile=$(cmd.exe /C 'echo %USERPROFILE%' </dev/null 2>/dev/null | tr -d '\r') || return 0
    wsl_dir=$(wslpath -u "$user_profile" 2>/dev/null) || return 0
    wslconfig="$wsl_dir/.wslconfig"

    # Already configured — nothing to do
    if [ -f "$wslconfig" ] && grep -qiE '^\s*networkingMode\s*=\s*mirrored' "$wslconfig" 2>/dev/null; then
        return 0
    fi

    # Don't silently overwrite a different networkingMode the user set intentionally
    if grep -qiE '^\s*networkingMode\s*=' "$wslconfig" 2>/dev/null; then
        local current
        current=$(grep -iE '^\s*networkingMode\s*=' "$wslconfig" | head -1 | sed 's/.*=\s*//' | tr -d '\r')
        echo "Warning: .wslconfig has networkingMode=$current — Rider MCP needs 'mirrored' for WSL2 localhost forwarding." >&2
        echo "Edit $(wslpath -w "$wslconfig" 2>/dev/null || echo "$wslconfig") and set networkingMode=mirrored, then run 'wsl --shutdown'." >&2
        return 0
    fi

    echo "Configuring WSL2 networkingMode=mirrored for localhost forwarding..." >&2

    # Back up before modifying
    if [ -f "$wslconfig" ]; then
        cp "$wslconfig" "${wslconfig}.bak" 2>/dev/null || true
    fi

    local write_ok=false
    if [ ! -f "$wslconfig" ]; then
        printf '[wsl2]\r\nnetworkingMode=mirrored\r\n' > "$wslconfig" && write_ok=true
    elif grep -qiE '^\s*\[wsl2\]' "$wslconfig" 2>/dev/null; then
        sed -i '/^\s*\[wsl2\]/a networkingMode=mirrored\r' "$wslconfig" && write_ok=true
    else
        printf '\r\n[wsl2]\r\nnetworkingMode=mirrored\r\n' >> "$wslconfig" && write_ok=true
    fi

    local display_path
    display_path=$(wslpath -w "$wslconfig" 2>/dev/null || echo "$wslconfig")
    if [ "$write_ok" = true ]; then
        echo "Added networkingMode=mirrored to $display_path" >&2
        echo ">>> WSL restart required: run 'wsl --shutdown' from PowerShell, then relaunch. <<<" >&2
        WSLCONFIG_CHANGED=true
    else
        echo "Warning: Failed to update $display_path — set networkingMode=mirrored manually." >&2
    fi
}

WSLCONFIG_CHANGED=false
ensure_wsl_networking || true

# If .wslconfig was just modified, start in setup-notice mode instead of
# trying to connect to Rider (which will fail until WSL is restarted).
if [ "$WSLCONFIG_CHANGED" = true ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    exec python3 "$SCRIPT_DIR/mcp-http-proxy.py" --wsl-setup-notice
fi

# --- Detect which Rider is running ---
is_linux_rider_running() {
    ss -tlnp 2>/dev/null | grep -qE '(remote-dev-serv|rider|Rider)' && return 0
    pgrep -f 'remote-dev-server' >/dev/null 2>&1 && return 0
    return 1
}

# Check Windows Rider process (capture first to avoid SIGPIPE with pipefail)
is_windows_rider_running() {
    local tasklist
    tasklist=$(cmd.exe /C "tasklist /FO CSV /NH" </dev/null 2>/dev/null | tr -d '\r') || true
    echo "$tasklist" | grep -aqiE 'rider64\.exe|Rider\.Backend\.exe' && return 0
    return 1
}

if is_linux_rider_running; then
    MODE="linux"
elif is_windows_rider_running; then
    MODE="windows"
else
    echo "Error: No running JetBrains Rider detected" >&2
    exit 1
fi

echo "Rider detected (mode: $MODE)" >&2

# --- Detect Rider MCP port ---
detect_mcp_port_linux() {
    ss -tlnp 2>/dev/null | while IFS= read -r line; do
        local port
        port=$(echo "$line" | grep -oP '127\.0\.0\.1:\K[0-9]+' || true)
        [ -z "$port" ] && continue
        if [ "$port" -ge 64342 ] && [ "$port" -le 65000 ]; then
            if echo "$line" | grep -qE '(remote-dev-serv|rider|Rider)'; then
                echo "$port"
                return 0
            fi
        fi
    done
    return 1
}

detect_mcp_port_windows() {
    local tasklist_output
    tasklist_output=$(cmd.exe /C "tasklist /FO CSV /NH" </dev/null 2>/dev/null | tr -d '\r') || true

    local line port pid
    while IFS= read -r line; do
        port=$(echo "$line" | awk '{ split($2,a,":"); print a[length(a)] }')
        pid=$(echo "$line" | awk '{ print $NF }')
        if [ -n "$pid" ] && echo "$tasklist_output" | grep -qE "\"(rider64\.exe|Rider\.Backend\.exe)\",\"$pid\""; then
            echo "$port"
            return 0
        fi
    done < <(cmd.exe /C "netstat -ano" </dev/null 2>/dev/null | tr -d '\r' \
        | awk '/LISTENING/ { split($2,a,":"); p=a[length(a)]; if (p>=64342 && p<=65000) print }')

    return 1
}

if [ -n "${IJ_MCP_SERVER_PORT:-}" ]; then
    echo "Using explicit port: $IJ_MCP_SERVER_PORT" >&2
else
    MAX_RETRIES=5
    RETRY_DELAY=2
    for i in $(seq 1 $MAX_RETRIES); do
        if [ "$MODE" = "linux" ]; then
            MCP_PORT=$(detect_mcp_port_linux) || true
        else
            MCP_PORT=$(detect_mcp_port_windows) || true
        fi
        if [ -n "${MCP_PORT:-}" ]; then
            export IJ_MCP_SERVER_PORT="$MCP_PORT"
            echo "Auto-detected Rider MCP port: $IJ_MCP_SERVER_PORT" >&2
            break
        fi
        if [ "$i" -lt "$MAX_RETRIES" ]; then
            echo "Waiting for Rider MCP port (attempt $i/$MAX_RETRIES)..." >&2
            sleep $RETRY_DELAY
        fi
    done

    if [ -z "${IJ_MCP_SERVER_PORT:-}" ]; then
        echo "Error: Could not detect Rider MCP port after $MAX_RETRIES attempts." >&2
        echo "Is Rider running with MCP enabled? Set IJ_MCP_SERVER_PORT manually or enable MCP in Rider settings." >&2
        exit 1
    fi
fi

# --- Resolve project path for multi-project disambiguation ---
PROJECT_PATH=""
if [ "$MODE" = "windows" ]; then
    PROJECT_PATH=$(wslpath -w "$PWD" 2>/dev/null | tr '\\' '/') || true
else
    PROJECT_PATH="$PWD"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/mcp-http-proxy.py" "$IJ_MCP_SERVER_PORT" "$PROJECT_PATH"
