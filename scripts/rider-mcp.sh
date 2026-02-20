#!/bin/bash
# Auto-detect JetBrains Rider installation and launch its MCP stdio server.
# Finds the latest Rider version, constructs the classpath, detects the MCP port,
# and execs the Java process.

set -euo pipefail

# --- Find Rider installation ---
RIDER_DIR=""

# Standard install location
for d in "/mnt/c/Program Files/JetBrains/JetBrains Rider"*; do
    [ -d "$d" ] && RIDER_DIR="$d"
done

# Toolbox install location (fallback)
if [ -z "$RIDER_DIR" ]; then
    for d in /mnt/c/Users/*/AppData/Local/JetBrains/Toolbox/apps/rider/ch-0/*/; do
        [ -d "$d" ] && RIDER_DIR="$d"
    done
fi

if [ -z "$RIDER_DIR" ]; then
    echo "Error: JetBrains Rider installation not found" >&2
    exit 1
fi

JAVA_EXE="$RIDER_DIR/jbr/bin/java.exe"
if [ ! -f "$JAVA_EXE" ]; then
    echo "Error: java.exe not found at $JAVA_EXE" >&2
    exit 1
fi

# --- Build classpath (Windows paths, semicolon-separated) ---
CP=""
add_jar() {
    local win_path
    win_path=$(wslpath -w "$1")
    [ -z "$CP" ] && CP="$win_path" || CP="$CP;$win_path"
}

# MCP server frontend JARs
for jar in "$RIDER_DIR"/plugins/mcpserver/lib/*.jar; do
    [ -f "$jar" ] && add_jar "$jar"
done

# Dependency JARs
for jar in "$RIDER_DIR"/lib/util-8.jar \
           "$RIDER_DIR"/lib/module-intellij.libraries.ktor.*.jar \
           "$RIDER_DIR"/lib/module-intellij.libraries.kotlinx.*.jar; do
    [ -f "$jar" ] && add_jar "$jar"
done

if [ -z "$CP" ]; then
    echo "Error: No MCP server JARs found in $RIDER_DIR" >&2
    exit 1
fi

# --- Detect Rider MCP port ---
if [ -z "${IJ_MCP_SERVER_PORT:-}" ]; then
    PORT=$(powershell.exe -NoProfile -Command '
        try {
            $p = Get-Process rider64 -ErrorAction Stop
            (Get-NetTCPConnection -OwningProcess $p.Id -State Listen |
             Where-Object { $_.LocalPort -ne 63342 } |
             Select-Object -First 1).LocalPort
        } catch {}' 2>/dev/null | tr -d '\r\n')

    if [ -n "$PORT" ]; then
        export IJ_MCP_SERVER_PORT="$PORT"
    else
        echo "Warning: Rider not running, MCP port detection failed" >&2
    fi
fi

export WSLENV="IJ_MCP_SERVER_PORT"

exec "$JAVA_EXE" -classpath "$CP" com.intellij.mcpserver.stdio.McpStdioRunnerKt
