"""Tests for MCP server tools."""

import pytest
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engines.sqlite import SQLiteEngine
from src.config import DatabaseConfig
from src.server import create_server


def _get_text(result) -> str:
    """Extract text from CallToolResult."""
    return result.content[0].text


@pytest.fixture
async def server_with_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, FOREIGN KEY (user_id) REFERENCES users(id))")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com')")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@test.com')")
    conn.execute("INSERT INTO orders VALUES (1, 1, 99.99)")
    conn.execute("INSERT INTO orders VALUES (2, 1, 49.99)")
    conn.execute("INSERT INTO orders VALUES (3, 2, 149.99)")
    conn.commit()
    conn.close()

    engine = SQLiteEngine(path=db_path, read_only=True)
    await engine.connect()

    config = DatabaseConfig(url=f"sqlite:///{db_path}", read_only=True)
    server = await create_server(config, engine)
    return server, engine


@pytest.mark.asyncio
async def test_test_connection(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("test_connection", {})
    text = _get_text(result)
    assert "sqlite" in text.lower() or "connection" in text.lower()
    await engine.disconnect()


@pytest.mark.asyncio
async def test_list_tables(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("list_tables", {})
    text = _get_text(result)
    assert "users" in text
    assert "orders" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_inspect_table(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("inspect_table", {"table_name": "users"})
    text = _get_text(result)
    assert "id" in text
    assert "name" in text
    assert "Alice" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_query_select(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("query", {"sql": "SELECT * FROM users"})
    text = _get_text(result)
    assert "Alice" in text
    assert "Bob" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_query_blocked_write(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("query", {"sql": "INSERT INTO users VALUES (3, 'Hacker', 'h@h.com')"})
    text = _get_text(result)
    assert "BLOCKED" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_query_blocked_drop(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("query", {"sql": "DROP TABLE users"})
    text = _get_text(result)
    assert "BLOCKED" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_natural_query_count(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("natural_query", {"question": "kolik users"})
    text = _get_text(result)
    assert "count" in text.lower() or "2" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_profile_database(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("profile_database", {})
    text = _get_text(result)
    assert "users" in text
    assert "orders" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_schema_graph(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("schema_graph", {})
    text = _get_text(result)
    assert "mermaid" in text.lower() or "erDiagram" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_query_injection_blocked(server_with_db):
    server, engine = server_with_db
    result = await server.call_tool("query", {"sql": "SELECT * FROM users WHERE name = '' OR '1'='1'"})
    text = _get_text(result)
    assert "BLOCKED" in text
    await engine.disconnect()


@pytest.mark.asyncio
async def test_tool_count(server_with_db):
    server, engine = server_with_db
    tools = await server.list_tools()
    assert len(tools) == 7
    tool_names = [t.name for t in tools]
    assert "test_connection" in tool_names
    assert "list_tables" in tool_names
    assert "inspect_table" in tool_names
    assert "query" in tool_names
    assert "natural_query" in tool_names
    assert "profile_database" in tool_names
    assert "schema_graph" in tool_names
    await engine.disconnect()
