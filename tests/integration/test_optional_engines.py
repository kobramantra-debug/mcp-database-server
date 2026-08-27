"""Integration tests for optional engines (PostgreSQL, MySQL).

These run against live docker containers. They are skipped automatically
when the target database is unreachable.
"""

import pytest
import socket


def _reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


PG_HOST, PG_PORT = "localhost", 15432
MYSQL_HOST, MYSQL_PORT = "localhost", 13306


pg = pytest.mark.skipif(
    not _reachable(PG_HOST, PG_PORT),
    reason=f"PostgreSQL not reachable at {PG_HOST}:{PG_PORT}",
)
mysql = pytest.mark.skipif(
    not _reachable(MYSQL_HOST, MYSQL_PORT),
    reason=f"MySQL not reachable at {MYSQL_HOST}:{MYSQL_PORT}",
)


# ---------------- PostgreSQL ----------------

@pg
@pytest.mark.asyncio
async def test_pg_connection(pg_engine):
    info = await pg_engine.get_db_info()
    assert info.engine == "postgresql"
    assert "PostgreSQL" in info.version


@pg
@pytest.mark.asyncio
async def test_pg_tables(pg_engine):
    tables = await pg_engine.get_tables()
    names = [t.name for t in tables]
    assert {"users", "products", "orders"} <= set(names)


@pg
@pytest.mark.asyncio
async def test_pg_table_detail(pg_engine):
    detail = await pg_engine.get_table_detail("users")
    col_names = [c.name for c in detail.columns]
    assert "id" in col_names and "name" in col_names
    detail_orders = await pg_engine.get_table_detail("orders")
    assert len(detail_orders.foreign_keys) >= 2


@pg
@pytest.mark.asyncio
async def test_pg_query(pg_engine):
    result = await pg_engine.execute_query("SELECT * FROM users ORDER BY id")
    assert result.row_count == 3
    assert result.rows[0]["name"] == "Alice"


@pg
@pytest.mark.asyncio
async def test_pg_query_named_params(pg_engine):
    sql = "SELECT * FROM users WHERE id = :uid"
    result = await pg_engine.execute_query(sql, {"uid": 2})
    assert result.row_count == 1
    assert result.rows[0]["name"] == "Bob"


@pg
@pytest.mark.asyncio
async def test_pg_join(pg_engine):
    result = await pg_engine.execute_query(
        "SELECT u.name, p.name AS product FROM orders o "
        "JOIN users u ON u.id = o.user_id "
        "JOIN products p ON p.id = o.product_id "
        "ORDER BY o.id"
    )
    assert result.row_count == 4


# ---------------- MySQL ----------------

@mysql
@pytest.mark.asyncio
async def test_mysql_connection(mysql_engine):
    info = await mysql_engine.get_db_info()
    assert info.engine == "mysql"


@mysql
@pytest.mark.asyncio
async def test_mysql_tables(mysql_engine):
    tables = await mysql_engine.get_tables()
    names = [t.name for t in tables]
    assert {"users", "products", "orders"} <= set(names)


@mysql
@pytest.mark.asyncio
async def test_mysql_table_detail(mysql_engine):
    detail = await mysql_engine.get_table_detail("users")
    col_names = [c.name for c in detail.columns]
    assert "id" in col_names and "name" in col_names
    detail_orders = await mysql_engine.get_table_detail("orders")
    assert len(detail_orders.foreign_keys) >= 2


@mysql
@pytest.mark.asyncio
async def test_mysql_query(mysql_engine):
    result = await mysql_engine.execute_query("SELECT * FROM users ORDER BY id")
    assert result.row_count == 3
    assert result.rows[0]["name"] == "Alice"


@mysql
@pytest.mark.asyncio
async def test_mysql_query_named_params(mysql_engine):
    sql = "SELECT * FROM users WHERE id = :uid"
    result = await mysql_engine.execute_query(sql, {"uid": 3})
    assert result.row_count == 1
    assert result.rows[0]["name"] == "Carol"


@mysql
@pytest.mark.asyncio
async def test_mysql_join(mysql_engine):
    result = await mysql_engine.execute_query(
        "SELECT u.name, p.name AS product FROM orders o "
        "JOIN users u ON u.id = o.user_id "
        "JOIN products p ON p.id = o.product_id "
        "ORDER BY o.id"
    )
    assert result.row_count == 4