#!/usr/bin/env python3
"""Stdio-to-Streamable-HTTP proxy for JetBrains Rider MCP server.

Bridges Claude Code's stdio MCP transport to Rider's streamable-http endpoint.
Reads JSON-RPC from stdin, POSTs to http://127.0.0.1:{port}/stream,
and writes responses to stdout. Also maintains a GET SSE connection
for server-initiated notifications.
"""

import http.client
import json
import os
import sys
import threading
import time


PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_CONFIG = os.path.join(PLUGIN_ROOT, "tools.json")


def _log(msg):
    print(f"[mcp-http-proxy] {msg}", file=sys.stderr)


def load_tools_config():
    """Load allowed/forbidden tool sets from tools.json.

    If allowed is set, only those tools are exposed.
    Forbidden tools are always removed, even if also in allowed.
    If neither is set, all tools pass through unfiltered.
    """
    if not os.path.exists(TOOLS_CONFIG):
        _log(f"No {TOOLS_CONFIG} found — all Rider tools will be exposed unfiltered")
        return None, set()

    try:
        with open(TOOLS_CONFIG) as f:
            cfg = json.load(f)
    except PermissionError:
        _log(f"ERROR: Cannot read {TOOLS_CONFIG} — permission denied. "
             f"Fix with: chmod 644 {TOOLS_CONFIG}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        _log(f"ERROR: {TOOLS_CONFIG} contains invalid JSON at line {e.lineno}: {e.msg}. "
             f"Validate with: python3 -m json.tool {TOOLS_CONFIG}")
        sys.exit(1)

    if not isinstance(cfg, dict):
        _log(f"ERROR: {TOOLS_CONFIG} must be a JSON object with 'allowed' and/or 'forbidden' arrays. "
             f"Got {type(cfg).__name__} instead.")
        sys.exit(1)

    allowed = None
    forbidden = set()

    for key in cfg:
        if key not in ("allowed", "forbidden"):
            _log(f"WARNING: Unknown key '{key}' in {TOOLS_CONFIG} — ignored. "
                 f"Valid keys: 'allowed', 'forbidden'")

    for key in ("allowed", "forbidden"):
        value = cfg.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            _log(f"ERROR: '{key}' in {TOOLS_CONFIG} must be an array of tool names. "
                 f"Got {type(value).__name__} instead.")
            sys.exit(1)
        bad = [v for v in value if not isinstance(v, str)]
        if bad:
            _log(f"ERROR: '{key}' in {TOOLS_CONFIG} contains non-string entries: {bad}. "
                 f"All entries must be tool name strings.")
            sys.exit(1)

    if cfg.get("allowed"):
        allowed = set(cfg["allowed"])
    if cfg.get("forbidden"):
        forbidden = set(cfg["forbidden"])

    overlap = (allowed or set()) & forbidden
    if overlap:
        _log(f"WARNING: Tools in both 'allowed' and 'forbidden': {sorted(overlap)} — "
             f"these will be blocked ('forbidden' wins)")

    if allowed is not None:
        _log(f"Tool filter: {len(allowed)} allowed, {len(forbidden)} forbidden")
    elif forbidden:
        _log(f"Tool filter: all allowed except {len(forbidden)} forbidden")

    return allowed, forbidden


ALLOWED_TOOLS, FORBIDDEN_TOOLS = load_tools_config()

WSL_SETUP_NOTICE = (
    "Rider MCP auto-configured your .wslconfig with networkingMode=mirrored.\n"
    "\n"
    "To complete setup:\n"
    "1. Open PowerShell and run: wsl --shutdown\n"
    "2. Relaunch your WSL terminal\n"
    "3. Start a new Claude Code session\n"
    "\n"
    "Rider MCP tools will be available after the restart."
)


def run_setup_notice_mode():
    """Standalone MCP server that surfaces the WSL restart notice to the user."""
    def write(msg):
        sys.stdout.buffer.write((json.dumps(msg) + "\n").encode())
        sys.stdout.buffer.flush()

    for raw_line in sys.stdin.buffer:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            write({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rider-mcp", "version": "1.0"},
                },
            })
        elif method == "notifications/initialized":
            pass  # no-op
        elif method == "tools/list":
            write({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": [{
                    "name": "rider_setup_status",
                    "description": (
                        "WSL restart required — .wslconfig was updated with "
                        "networkingMode=mirrored. Call this tool for setup instructions."
                    ),
                    "inputSchema": {"type": "object", "properties": {}},
                }]},
            })
        elif method == "tools/call":
            write({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": WSL_SETUP_NOTICE}]},
            })
        elif msg_id is not None:
            write({
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": "WSL restart required"},
            })


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--wsl-setup-notice":
        run_setup_notice_mode()
        return

    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = int(os.environ.get("IJ_MCP_SERVER_PORT", "64342"))

    project_path = sys.argv[2] if len(sys.argv) > 2 else ""

    host = "127.0.0.1"
    endpoint = "/stream"

    session_id = None
    session_lock = threading.Lock()
    stdout_lock = threading.Lock()

    def write_stdout(data: bytes):
        with stdout_lock:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()

    def write_message(msg):
        line = json.dumps(msg) + "\n"
        write_stdout(line.encode())

    def get_session_id():
        with session_lock:
            return session_id

    def set_session_id(sid):
        nonlocal session_id
        with session_lock:
            session_id = sid

    def read_sse_events(resp):
        """Parse SSE events from an HTTP response, yielding JSON messages."""
        event_data = []
        while True:
            raw_line = resp.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("data: "):
                event_data.append(line[6:])
            elif line == "" and event_data:
                data = "\n".join(event_data)
                event_data = []
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    pass
        if event_data:
            data = "\n".join(event_data)
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                pass

    def notification_listener():
        """GET SSE connection for server-initiated notifications."""
        while True:
            sid = get_session_id()
            if not sid:
                time.sleep(1)
                continue
            try:
                conn = http.client.HTTPConnection(host, port, timeout=300)
                headers = {"Accept": "text/event-stream", "Mcp-Session-Id": sid}
                conn.request("GET", endpoint, headers=headers)
                resp = conn.getresponse()
                if resp.status == 200 and "text/event-stream" in resp.getheader("Content-Type", ""):
                    for msg in read_sse_events(resp):
                        write_message(msg)
                else:
                    resp.read()
                conn.close()
            except (ConnectionError, OSError, http.client.HTTPException):
                pass
            except Exception as e:
                _log(f"Notification listener error: {e}")
            # Always pause before reconnecting to avoid busy-looping
            # when the server closes SSE connections quickly
            time.sleep(2)

    def send_delete():
        """Send DELETE to terminate the session."""
        sid = get_session_id()
        if not sid:
            return
        try:
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("DELETE", endpoint, headers={"Mcp-Session-Id": sid})
            conn.getresponse().read()
            conn.close()
        except Exception:
            pass

    def inject_project_path(line):
        """Inject projectPath into tools/call arguments for multi-project disambiguation."""
        if not project_path:
            return line
        try:
            msg = json.loads(line)
            if msg.get("method") == "tools/call":
                args = msg.get("params", {}).get("arguments")
                if isinstance(args, dict) and "projectPath" not in args:
                    args["projectPath"] = project_path
                    return json.dumps(msg)
        except (json.JSONDecodeError, AttributeError):
            pass
        return line

    def filter_tools_response(msg):
        """Filter tools/list responses using allowed/forbidden from tools.json."""
        tools = msg.get("result", {}).get("tools")
        if tools is None:
            return msg
        before = len(tools)
        filtered = tools
        if ALLOWED_TOOLS is not None:
            filtered = [t for t in filtered if t.get("name") in ALLOWED_TOOLS]
        if FORBIDDEN_TOOLS:
            filtered = [t for t in filtered if t.get("name") not in FORBIDDEN_TOOLS]
        removed = before - len(filtered)
        if removed:
            _log(f"Filtered tools: {len(filtered)} exposed, {removed} hidden")
        msg["result"]["tools"] = filtered
        return msg

    def maybe_filter_response(msg, request_method):
        """Filter tools/list responses to only include allowed tools."""
        if request_method == "tools/list":
            return filter_tools_response(msg)
        return msg

    _log(f"Proxying stdio to http://{host}:{port}{endpoint}")
    if project_path:
        _log(f"Project path: {project_path}")

    # Delay notification listener until we have a session ID from the first POST
    t_notify = threading.Thread(target=notification_listener, daemon=True)
    t_notify.start()

    try:
        for raw_line in sys.stdin.buffer:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            line = inject_project_path(line)

            # Track request method so we can filter the response
            request_method = ""
            try:
                request_method = json.loads(line).get("method", "")
            except (json.JSONDecodeError, AttributeError):
                pass

            try:
                conn = http.client.HTTPConnection(host, port, timeout=300)
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                }
                sid = get_session_id()
                if sid:
                    headers["Mcp-Session-Id"] = sid

                conn.request("POST", endpoint, body=line.encode(), headers=headers)
                resp = conn.getresponse()

                new_sid = resp.getheader("Mcp-Session-Id")
                if new_sid:
                    set_session_id(new_sid)

                content_type = resp.getheader("Content-Type", "")

                if resp.status == 202:
                    resp.read()
                elif "text/event-stream" in content_type:
                    for msg in read_sse_events(resp):
                        write_message(maybe_filter_response(msg, request_method))
                else:
                    body = resp.read().decode("utf-8", errors="replace")
                    if body.strip():
                        try:
                            msg = json.loads(body)
                            write_message(maybe_filter_response(msg, request_method))
                        except json.JSONDecodeError:
                            _log(f"Bad JSON from Rider: {body[:200]}")

                conn.close()
            except (ConnectionError, OSError, http.client.HTTPException) as e:
                _log(f"Request error: {e}")
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        send_delete()


if __name__ == "__main__":
    main()
