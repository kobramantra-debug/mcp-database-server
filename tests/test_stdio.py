"""STDIO handshake test for Docker."""

import os
import subprocess
import json
import sys
import time

from mcp_database_universal import __version__

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_stdio(messages, per_msg_wait=0.3):
    """Start the server, send JSON-RPC messages one by one, collect responses.

    Messages are written incrementally so the server has time to process each
    notification before stdin closes (otherwise responses can race with EOF).
    """
    proc = subprocess.Popen(
        [
            "docker", "run", "--rm", "-i",
            "-e", "DATABASE_URL=sqlite:///:memory:",
            "mcp-db-test:latest",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdin is not None and proc.stdout is not None
    for msg in messages:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        time.sleep(per_msg_wait)
    proc.stdin.close()

    # read incrementally with a deadline so a slow first response
    # doesn't race with pipe teardown
    deadline = time.time() + 30
    out_chunks = []
    while time.time() < deadline:
        chunk = proc.stdout.read(1)
        if chunk:
            out_chunks.append(chunk)
            continue
        # no data right now: give the process a moment, then stop if it exited
        proc.poll()
        if proc.returncode is not None:
            break
        time.sleep(0.05)
    stdout = "".join(out_chunks)

    responses = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return responses


def test_docker_build():
    result = subprocess.run(
        ["docker", "build", "-t", "mcp-db-test:latest", "."],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, f"Docker build failed:\n{result.stderr}"


def test_stdio_handshake():
    responses = _run_stdio([
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            },
        },
    ])

    assert len(responses) >= 1, f"No valid JSON-RPC responses found in stdout."

    init_response = responses[0]
    assert init_response.get("jsonrpc") == "2.0"
    assert init_response.get("id") == 1
    assert "result" in init_response
    assert "protocolVersion" in init_response["result"]
    assert "capabilities" in init_response["result"]
    assert "serverInfo" in init_response["result"]

    assert init_response["result"]["serverInfo"]["name"] == "mcp-database-server"
    assert init_response["result"]["serverInfo"]["version"] == __version__


def test_stdio_tools_list():
    responses = _run_stdio([
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])

    assert len(responses) >= 2, f"Expected 2+ responses, got {len(responses)}"

    tools_response = None
    for r in responses:
        if r.get("id") == 2:
            tools_response = r
            break

    assert tools_response is not None, "No tools/list response found"
    assert "result" in tools_response
    tools = tools_response["result"]["tools"]
    assert len(tools) == 7, f"Expected 7 tools, got {len(tools)}"

    tool_names = [t["name"] for t in tools]
    assert "test_connection" in tool_names
    assert "query" in tool_names
    assert "natural_query" in tool_names
