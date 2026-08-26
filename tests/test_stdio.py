"""STDIO handshake test for Docker."""

import subprocess
import json
import sys


def test_docker_build():
    result = subprocess.run(
        ["docker", "build", "-t", "mcp-db-test:latest", "."],
        cwd=r"C:\Users\lukas\Desktop\mcp\mcp-db",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Docker build failed:\n{result.stderr}"


def test_stdio_handshake():
    init_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        }
    }) + "\n"

    result = subprocess.run(
        [
            "docker", "run", "--rm", "-i",
            "-e", "DATABASE_URL=sqlite:///:memory:",
            "mcp-db-test:latest",
        ],
        input=init_msg,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0 or result.returncode == -15, \
        f"Docker STDIO failed (exit {result.returncode}):\nstderr: {result.stderr}"

    lines = result.stdout.strip().split("\n")
    responses = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    assert len(responses) >= 1, f"No valid JSON-RPC responses found in stdout. Raw: {result.stdout[:500]}"

    init_response = responses[0]
    assert init_response.get("jsonrpc") == "2.0"
    assert init_response.get("id") == 1
    assert "result" in init_response
    assert "protocolVersion" in init_response["result"]
    assert "capabilities" in init_response["result"]
    assert "serverInfo" in init_response["result"]

    assert init_response["result"]["serverInfo"]["name"] == "mcp-database-server"
    assert init_response["result"]["serverInfo"]["version"] == "0.1.0"


def test_stdio_tools_list():
    init_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        }
    }) + "\n"

    notify_msg = json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }) + "\n"

    tools_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }) + "\n"

    full_input = init_msg + notify_msg + tools_msg

    result = subprocess.run(
        [
            "docker", "run", "--rm", "-i",
            "-e", "DATABASE_URL=sqlite:///:memory:",
            "mcp-db-test:latest",
        ],
        input=full_input,
        capture_output=True,
        text=True,
        timeout=30,
    )

    lines = result.stdout.strip().split("\n")
    responses = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            continue

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
