"""Tests for LLM formatter."""

import pytest
from src.formatters.llm import LLMFormatter
from src.config import DatabaseConfig
from src.engines.base import (
    DBInfo, TableInfo, TableDetail, TableStats, ColumnInfo,
    ForeignKeyInfo, IndexInfo, QueryResult,
)


@pytest.fixture
def formatter():
    config = DatabaseConfig(url="sqlite:///:memory:", max_output_bytes=50000)
    return LLMFormatter(config)


def test_translate_type_integer(formatter):
    assert "integer" in formatter.translate_type("INTEGER")


def test_translate_type_varchar(formatter):
    result = formatter.translate_type("VARCHAR(255)")
    assert "text" in result
    assert "255" in result


def test_translate_type_text(formatter):
    assert "text" in formatter.translate_type("TEXT")


def test_format_number(formatter):
    assert formatter.format_number(1234567) == "1,234,567"
    assert formatter.format_number(3.14) == "3.14"
    assert formatter.format_number(None) == "(empty)"


def test_format_value(formatter):
    assert formatter.format_value(None) == "(empty)"
    assert formatter.format_value(42) == "42"
    assert formatter.format_value("hello") == "hello"


def test_format_db_info(formatter):
    info = DBInfo(engine="sqlite", version="3.45.0", name=":memory:", size_approx="~0 KB")
    result = formatter.format_db_info(info)
    assert "sqlite" in result
    assert "3.45.0" in result


def test_format_table_list_empty(formatter):
    result = formatter.format_table_list([])
    assert "No tables" in result


def test_format_table_list(formatter):
    tables = [
        TableInfo(name="users", row_count=100, column_count=5, foreign_keys_in=0, foreign_keys_out=2),
        TableInfo(name="orders", row_count=500, column_count=4, foreign_keys_in=1, foreign_keys_out=0),
    ]
    result = formatter.format_table_list(tables)
    assert "users" in result
    assert "orders" in result
    assert "100" in result
    assert "500" in result


def test_format_table_detail(formatter):
    detail = TableDetail(
        name="users",
        columns=[
            ColumnInfo(name="id", type="INTEGER", nullable=False, is_primary_key=True),
            ColumnInfo(name="name", type="VARCHAR(100)", nullable=False),
        ],
        foreign_keys=[],
        indexes=[IndexInfo(name="idx_name", columns=["name"], unique=False)],
        sample_data=[{"id": 1, "name": "Alice"}],
        stats=TableStats(row_count=1, total_size="~4 KB"),
    )
    result = formatter.format_table_detail(detail)
    assert "users" in result
    assert "id" in result
    assert "name" in result
    assert "PK" in result
    assert "Alice" in result


def test_format_query_result(formatter):
    result = QueryResult(
        columns=["id", "name"],
        rows=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        row_count=2,
        truncated=False,
        execution_time_ms=15,
        sql="SELECT * FROM users",
    )
    output = formatter.format_query_result(result)
    assert "SELECT * FROM users" in output
    assert "Alice" in output
    assert "Bob" in output
    assert "15ms" in output


def test_format_query_result_empty(formatter):
    result = QueryResult(
        columns=["id"],
        rows=[],
        row_count=0,
        sql="SELECT * FROM empty",
    )
    output = formatter.format_query_result(result)
    assert "No rows" in output


def test_format_query_result_with_warning(formatter):
    result = QueryResult(
        sql="SELECT 1",
        warning="Error: test",
    )
    output = formatter.format_query_result(result)
    assert "Error: test" in output


def test_truncate_for_llm(formatter):
    text = "x" * 100000
    result, truncated = formatter.truncate_for_llm(text)
    assert truncated is True
    assert "truncated" in result


def test_no_truncate_small(formatter):
    text = "small text"
    result, truncated = formatter.truncate_for_llm(text)
    assert truncated is False
    assert result == text


def test_format_schema_graph(formatter):
    result = formatter.format_schema_graph("erDiagram\n users ||--o{ orders : has")
    assert "mermaid" in result
    assert "users" in result
