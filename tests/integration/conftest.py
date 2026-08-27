"""Shared fixtures for integration tests.

Requires running docker containers (see docker-compose.yml in this directory):
- PostgreSQL on localhost:15432 (test/test/testdb)
- MySQL on localhost:13306 (test/test/testdb)

Tests are skipped automatically when the database is not reachable.
"""

import asyncio
import os
import pathlib
import pytest
from mcp_database_universal.engines.postgres import PostgresEngine
from mcp_database_universal.engines.mysql import MySQLEngine

_SCHEMA = (pathlib.Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


async def _run_statements(engine, statements):
    conn = engine._ensure_conn()
    for stmt in statements:
        try:
            if hasattr(conn, "cursor") and not hasattr(conn, "execute"):
                # pymysql-style: Connection.cursor() with sync execute
                cur = conn.cursor()
                cur.execute(stmt)
                if cur.description:
                    cur.fetchall()
                cur.close()
            else:
                # psycopg-style: await Connection.execute() -> AsyncCursor
                cur = await conn.execute(stmt)
                if hasattr(cur, "fetchall"):
                    await cur.fetchall()
        except Exception:
            pass
    if hasattr(conn, "commit"):
        if asyncio.iscoroutinefunction(conn.commit):
            await conn.commit()
        else:
            conn.commit()


async def _setup_db(engine):
    await _run_statements(engine, [s for s in _SCHEMA.split(";") if s.strip()])


async def _drop_tables_pg(engine):
    conn = engine._ensure_conn()
    try:
        if hasattr(conn, "cursor"):
            return
        cur = await conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        )
        names = [row[0] for row in await cur.fetchall()]
    except Exception:
        names = []
    for name in names:
        await _run_statements(engine, [f'DROP TABLE IF EXISTS "{name}" CASCADE'])


async def _drop_tables_mysql(engine):
    conn = engine._ensure_conn()
    try:
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        names = [row[0] for row in cur.fetchall()]
        cur.close()
    except Exception:
        names = []
    for name in names:
        await _run_statements(engine, [f"DROP TABLE IF EXISTS `{name}`"])


@pytest.fixture
async def pg_engine():
    writer = PostgresEngine(
        host=os.environ.get("TEST_PG_HOST", "localhost"),
        port=int(os.environ.get("TEST_PG_PORT", "15432")),
        database="testdb",
        user="test",
        password="test",
        read_only=False,
    )
    await writer.connect()
    try:
        await _drop_tables_pg(writer)
        await _setup_db(writer)
    except Exception:
        pass
    reader = PostgresEngine(
        host=os.environ.get("TEST_PG_HOST", "localhost"),
        port=int(os.environ.get("TEST_PG_PORT", "15432")),
        database="testdb",
        user="test",
        password="test",
        read_only=True,
    )
    await reader.connect()
    yield reader
    await reader.disconnect()
    await writer.disconnect()


@pytest.fixture
async def mysql_engine():
    writer = MySQLEngine(
        host=os.environ.get("TEST_MYSQL_HOST", "localhost"),
        port=int(os.environ.get("TEST_MYSQL_PORT", "13306")),
        database="testdb",
        user="test",
        password="test",
        read_only=False,
    )
    await writer.connect()
    try:
        await _drop_tables_mysql(writer)
        await _setup_db(writer)
    except Exception:
        pass
    reader = MySQLEngine(
        host=os.environ.get("TEST_MYSQL_HOST", "localhost"),
        port=int(os.environ.get("TEST_MYSQL_PORT", "13306")),
        database="testdb",
        user="test",
        password="test",
        read_only=True,
    )
    await reader.connect()
    yield reader
    await reader.disconnect()
    await writer.disconnect()