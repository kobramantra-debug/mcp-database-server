"""Tests for SQLite engine."""

import pytest
from src.engines.sqlite import SQLiteEngine
from src.engines.base import DBInfo, TableInfo, TableDetail, QueryResult


@pytest.mark.asyncio
async def test_connect_memory():
    engine = SQLiteEngine(path=":memory:", read_only=False)
    await engine.connect()
    info = await engine.get_db_info()
    assert info.engine == "sqlite"
    assert info.name == ":memory:"
    await engine.disconnect()


@pytest.mark.asyncio
async def test_connect_file(tmp_path):
    db_path = str(tmp_path / "test.db")
    engine = SQLiteEngine(path=db_path, read_only=False)
    await engine.connect()
    info = await engine.get_db_info()
    assert info.engine == "sqlite"
    assert info.name == db_path
    await engine.disconnect()


@pytest.mark.asyncio
async def test_get_tables_empty():
    engine = SQLiteEngine(path=":memory:", read_only=False)
    await engine.connect()
    tables = await engine.get_tables()
    assert tables == []
    await engine.disconnect()


@pytest.mark.asyncio
async def test_get_tables_with_data(sample_db_path):
    engine = SQLiteEngine(path=sample_db_path, read_only=True)
    await engine.connect()
    tables = await engine.get_tables()
    names = [t.name for t in tables]
    assert "users" in names
    assert "products" in names
    assert "orders" in names
    await engine.disconnect()


@pytest.mark.asyncio
async def test_table_row_counts(sample_db_path):
    engine = SQLiteEngine(path=sample_db_path, read_only=True)
    await engine.connect()
    tables = await engine.get_tables()
    users = next(t for t in tables if t.name == "users")
    assert users.row_count == 3
    products = next(t for t in tables if t.name == "products")
    assert products.row_count == 3
    await engine.disconnect()


@pytest.mark.asyncio
async def test_table_detail_columns(sample_db_path):
    engine = SQLiteEngine(path=sample_db_path, read_only=True)
    await engine.connect()
    detail = await engine.get_table_detail("users")
    col_names = [c.name for c in detail.columns]
    assert "id" in col_names
    assert "name" in col_names
    assert "email" in col_names
    await engine.disconnect()


@pytest.mark.asyncio
async def test_table_detail_primary_key(sample_db_path):
    engine = SQLiteEngine(path=sample_db_path, read_only=True)
    await engine.connect()
    detail = await engine.get_table_detail("users")
    assert detail.primary_key == "id"
    pk_cols = [c for c in detail.columns if c.is_primary_key]
    assert len(pk_cols) == 1
    await engine.disconnect()


@pytest.mark.asyncio
async def test_table_detail_foreign_keys(sample_db_path):
    engine = SQLiteEngine(path=sample_db_path, read_only=True)
    await engine.connect()
    detail = await engine.get_table_detail("orders")
    assert len(detail.foreign_keys) == 2
    fk_cols = [fk.column for fk in detail.foreign_keys]
    assert "user_id" in fk_cols
    assert "product_id" in fk_cols
    await engine.disconnect()


@pytest.mark.asyncio
async def test_table_detail_sample_data(sample_db_path):
    engine = SQLiteEngine(path=sample_db_path, read_only=True)
    await engine.connect()
    detail = await engine.get_table_detail("users")
    assert len(detail.sample_data) == 3
    assert detail.sample_data[0]["name"] == "Alice"
    await engine.disconnect()


@pytest.mark.asyncio
async def test_execute_query_select():
    engine = SQLiteEngine(path=":memory:", read_only=False)
    await engine.connect()
    result = await engine.execute_query("SELECT 1 as num")
    assert result.row_count == 1
    assert result.columns == ["num"]
    assert result.rows[0]["num"] == 1
    await engine.disconnect()


@pytest.mark.asyncio
async def test_execute_query_with_params():
    engine = SQLiteEngine(path=":memory:", read_only=False)
    await engine.connect()
    result = await engine.execute_query(
        "SELECT * FROM (SELECT 1 as id, 'test' as name) WHERE id = :id",
        {"id": 1}
    )
    assert result.row_count == 1
    await engine.disconnect()


@pytest.mark.asyncio
async def test_execute_query_error():
    engine = SQLiteEngine(path=":memory:", read_only=False)
    await engine.connect()
    result = await engine.execute_query("SELECT * FROM nonexistent_table")
    assert result.warning is not None
    assert "Error" in result.warning
    await engine.disconnect()


@pytest.mark.asyncio
async def test_sample_data():
    engine = SQLiteEngine(path=":memory:", read_only=False)
    await engine.connect()
    result = await engine.get_sample_data("users", limit=5)
    assert result.row_count == 0  # empty table
    await engine.disconnect()


@pytest.mark.asyncio
async def test_read_only():
    engine = SQLiteEngine(path=":memory:", read_only=True)
    assert engine.is_read_only() is True
    engine2 = SQLiteEngine(path=":memory:", read_only=False)
    assert engine2.is_read_only() is False


@pytest.mark.asyncio
async def test_disconnect_without_connect():
    engine = SQLiteEngine(path=":memory:", read_only=False)
    await engine.disconnect()  # should not raise


@pytest.mark.asyncio
async def test_get_db_info_file_size(tmp_path):
    db_path = str(tmp_path / "sized.db")
    engine = SQLiteEngine(path=db_path, read_only=False)
    await engine.connect()
    await engine.execute_query("CREATE TABLE t (id INTEGER)")
    info = await engine.get_db_info()
    assert info.size_approx != "unknown"
    await engine.disconnect()
