"""Tests for safety layer."""

import pytest
from src.safety import SafetyValidator, QueryType


def test_select_approved():
    v = SafetyValidator(read_only=True)
    r = v.validate("SELECT * FROM users")
    assert r.approved is True
    assert r.query_type == QueryType.SAFE_READ


def test_insert_blocked_read_only():
    v = SafetyValidator(read_only=True)
    r = v.validate("INSERT INTO users VALUES (1, 'test')")
    assert r.approved is False
    assert r.query_type == QueryType.WRITE


def test_update_blocked_read_only():
    v = SafetyValidator(read_only=True)
    r = v.validate("UPDATE users SET name = 'test'")
    assert r.approved is False
    assert r.query_type == QueryType.WRITE


def test_delete_blocked_read_only():
    v = SafetyValidator(read_only=True)
    r = v.validate("DELETE FROM users WHERE id = 1")
    assert r.approved is False
    assert r.query_type == QueryType.WRITE


def test_drop_blocked_read_only():
    v = SafetyValidator(read_only=True)
    r = v.validate("DROP TABLE users")
    assert r.approved is False
    assert r.query_type == QueryType.DANGEROUS


def test_create_blocked_read_only():
    v = SafetyValidator(read_only=True)
    r = v.validate("CREATE TABLE test (id INT)")
    assert r.approved is False
    assert r.query_type == QueryType.DANGEROUS


def test_write_allowed_when_not_read_only():
    v = SafetyValidator(read_only=False)
    r = v.validate("INSERT INTO users VALUES (1, 'test')")
    assert r.approved is True
    assert r.query_type == QueryType.WRITE


def test_empty_query():
    v = SafetyValidator(read_only=True)
    r = v.validate("")
    assert r.approved is False


def test_unknown_query():
    v = SafetyValidator(read_only=True)
    r = v.validate("BANANA FROM users")
    assert r.approved is False
    assert r.query_type == QueryType.UNKNOWN


def test_injection_or():
    v = SafetyValidator(read_only=True)
    r = v.validate("SELECT * FROM users WHERE name = '' OR '1'='1'")
    assert r.approved is False


def test_injection_semicolon():
    v = SafetyValidator(read_only=True)
    r = v.validate("SELECT 1; DROP TABLE users")
    assert r.approved is False


def test_injection_comment():
    v = SafetyValidator(read_only=True)
    r = v.validate("SELECT * FROM users -- comment")
    assert r.approved is False


def test_explain_approved():
    v = SafetyValidator(read_only=True)
    r = v.validate("EXPLAIN SELECT * FROM users")
    assert r.approved is True
    assert r.query_type == QueryType.SAFE_READ


def test_pragma_approved():
    v = SafetyValidator(read_only=True)
    r = v.validate("PRAGMA table_info(users)")
    assert r.approved is True


def test_ensure_limit_adds():
    v = SafetyValidator(read_only=True, max_rows=50)
    sql = v.ensure_limit("SELECT * FROM users")
    assert "LIMIT 50" in sql


def test_ensure_limit_no_double():
    v = SafetyValidator(read_only=True, max_rows=50)
    sql = v.ensure_limit("SELECT * FROM users LIMIT 10")
    assert sql == "SELECT * FROM users LIMIT 10"


def test_union_injection():
    v = SafetyValidator(read_only=True)
    r = v.validate("SELECT name FROM users UNION ALL SELECT password FROM admin")
    assert r.approved is False


def test_sleep_injection():
    v = SafetyValidator(read_only=True)
    r = v.validate("SELECT SLEEP(10)")
    assert r.approved is False


def test_with_select_approved():
    v = SafetyValidator(read_only=True)
    r = v.validate("WITH cte AS (SELECT 1) SELECT * FROM cte")
    assert r.approved is True
