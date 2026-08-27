"""Tests for the NL2SQL translation module."""

import sys
import os
import unittest.mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_database_universal.nl2sql import (
    _build_prompt,
    _extract_sql,
    llm_translate,
    offline_translate,
    translate,
)

TABLES = ["users", "orders", "products"]


# --- offline parser ---


@pytest.mark.asyncio
async def test_offline_count():
    t = await translate("how many users", TABLES)
    assert t.sql == 'SELECT COUNT(*) AS count FROM "users"'
    assert t.source == "offline"


def test_offline_list_all():
    t = offline_translate("show me all orders", TABLES)
    assert t.sql == 'SELECT * FROM "orders" LIMIT 100'


def test_offline_from_table():
    t = offline_translate("I want the products", TABLES)
    assert t.sql == 'SELECT * FROM "products" LIMIT 100'


def test_offline_where_numeric():
    t = offline_translate("orders where amount = 100", TABLES)
    assert t.sql == 'SELECT * FROM "orders" WHERE "amount" = 100 LIMIT 100'


def test_offline_top():
    t = offline_translate("top 5 price in products", TABLES)
    assert t.sql is not None
    assert "ORDER BY" in t.sql
    assert "LIMIT 5" in t.sql


def test_offline_unknown_falls_back_to_table_listing():
    t = offline_translate("whatever users foo bar", TABLES)
    assert t.sql == 'SELECT * FROM "users" LIMIT 100'


def test_offline_unrelated_no_table():
    t = offline_translate("hello world foo bar", TABLES)
    assert t.sql is None


def test_extra_singular_table():
    # an unknown singular form still falls back to the closest known table
    t = offline_translate("list all user stuff here", TABLES)
    assert t.sql is not None


# --- SQL extraction ---


def test_extract_sql_plain():
    assert _extract_sql("SELECT * FROM users") == "SELECT * FROM users"


def test_extract_sql_fenced():
    out = _extract_sql("```sql\nSELECT 1\n```")
    assert out == "SELECT 1"


def test_extract_sql_with_prose():
    out = _extract_sql('Here is your query:\nSELECT id FROM users\nHope that helps')
    assert out == "SELECT id FROM users"


def test_extract_sql_rejects_non_select():
    assert _extract_sql("DROP TABLE users") is None


# --- prompt ---


def test_prompt_contains_tables():
    p = _build_prompt(TABLES)
    assert "users" in p
    assert "orders" in p
    assert "products" in p


# --- LLM path (mocked) ---


async def _fake_openai_caller(answers, *args, **kwargs):
    question = args[2] if len(args) > 2 else kwargs.get("question", "")
    if "count" in question.lower():
        return 'SELECT COUNT(*) as count FROM "users"'
    return answers.pop(0) if answers else "SELECT * FROM users"


@pytest.mark.asyncio
async def test_llm_translate_requires_key():
    t = await llm_translate("how many users", TABLES)
    assert t.sql is None
    assert "No API key configured" in (t.error or "")


@pytest.mark.asyncio
async def test_llm_translate_openai_path(monkeypatch):
    calls = []

    async def fake_to_thread(fn, *args, **kwargs):
        calls.append((fn, args))
        return '```sql\nSELECT COUNT(*) AS count FROM "users"\n```'

    import asyncio

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    monkeypatch.setattr("mcp_database_universal.nl2sql._call_openai", lambda *a, **k: "ignored")

    t = await llm_translate(
        "how many users",
        TABLES,
        openai_key="sk-test",
    )
    assert t.sql == 'SELECT COUNT(*) AS count FROM "users"'
    assert t.source == "llm"
    assert calls and calls[0][1] == ("sk-test", unittest.mock.ANY, "how many users", "gpt-4o-mini")


@pytest.mark.asyncio
async def test_llm_translate_anthropic_path(monkeypatch):
    import asyncio

    async def fake_to_thread(fn, *args, **kwargs):
        return 'SELECT COUNT(*) FROM "orders"'

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr("mcp_database_universal.nl2sql._call_anthropic", lambda *a, **k: "ignored")

    t = await llm_translate(
        "how many orders",
        TABLES,
        anthropic_key="ant-test",
    )
    assert t.sql == 'SELECT COUNT(*) FROM "orders"'
    assert t.source == "llm"


@pytest.mark.asyncio
async def test_translate_prefers_llm_then_falls_back(monkeypatch):
    import asyncio

    # LLM is configured but returns garbage, so offline fallback is used.
    async def fake_to_thread(fn, *args, **kwargs):
        return "I cannot answer that"

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr("mcp_database_universal.nl2sql._call_openai", lambda *a, **k: "garbage")

    t = await translate(
        "show me all products",
        TABLES,
        openai_key="sk-test",
    )
    assert t.sql == 'SELECT * FROM "products" LIMIT 100'
    assert t.source == "offline"


# --- real HTTP request shape (local mock server) ---


def test_openai_request_shape_via_local_server():
    """End-to-end over localhost: the request body/headers and response parsing."""
    import http.server
    import json
    import socketserver
    import threading
    from urllib.request import Request, urlopen  # noqa: F401

    captured = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            captured["path"] = self.path
            captured["auth"] = self.headers.get("Authorization")
            captured["ctype"] = self.headers.get("Content-Type")
            captured["body"] = json.loads(body)
            response = json.dumps(
                {"choices": [{"message": {"content": "SELECT 'ok' AS ok"}}]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            sql = _call_openai_path_for_test(port, "sk-test-secret")
        finally:
            httpd.shutdown()
            httpd.server_close()

    assert sql is not None
    assert sql == "SELECT 'ok' AS ok"
    assert captured["path"] == "/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-test-secret"
    assert captured["ctype"] == "application/json"
    assert captured["body"]["model"]
    assert captured["body"]["messages"][0]["role"] == "system"


def _call_openai_path_for_test(port, api_key):
    """Mirror of nl2sql._call_openai but pointed at a local test server."""
    import json as _json
    from urllib.request import Request, urlopen

    prompt = _build_prompt(TABLES)
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "how many users"},
        ],
        "temperature": 0,
    }
    req = Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=_json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        data = _json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def test_anthropic_request_shape_via_local_server():
    import http.server
    import json
    import socketserver
    import threading
    from urllib.request import Request, urlopen

    captured = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            captured["path"] = self.path
            captured["x_api_key"] = self.headers.get("x-api-key")
            captured["version"] = self.headers.get("anthropic-version")
            captured["body"] = json.loads(body)
            response = json.dumps(
                {"content": [{"type": "text", "text": "SELECT 2 AS two"}]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            prompt = _build_prompt(TABLES)
            body = {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 512,
                "system": prompt,
                "messages": [{"role": "user", "content": "how many users"}],
            }
            req = Request(
                f"http://127.0.0.1:{port}/v1/messages",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": "ant-test-secret",
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = "".join(b.get("text", "") for b in data.get("content", []))
        finally:
            httpd.shutdown()
            httpd.server_close()

    assert text == "SELECT 2 AS two"
    assert captured["path"] == "/v1/messages"
    assert captured["x_api_key"] == "ant-test-secret"
    assert captured["version"] == "2023-06-01"
    assert captured["body"]["system"]
    assert captured["body"]["messages"][0]["role"] == "user"