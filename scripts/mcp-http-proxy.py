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


def _log(msg):
    print(f"[mcp-http-proxy] {msg}", file=sys.stderr)


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
                        write_message(msg)
                else:
                    body = resp.read().decode("utf-8", errors="replace")
                    if body.strip():
                        try:
                            msg = json.loads(body)
                            write_message(msg)
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
