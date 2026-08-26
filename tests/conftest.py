"""Shared test fixtures — in-memory SQLite database."""

import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engines.sqlite import SQLiteEngine
from src.config import DatabaseConfig


@pytest.fixture
def sample_db_path(tmp_path):
    """Create a temporary SQLite database with sample data."""
    import sqlite3
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            age INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL,
            category TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    conn.execute("INSERT INTO users (name, email, age) VALUES ('Alice', 'alice@test.com', 30)")
    conn.execute("INSERT INTO users (name, email, age) VALUES ('Bob', 'bob@test.com', 25)")
    conn.execute("INSERT INTO users (name, email, age) VALUES ('Charlie', NULL, 35)")
    conn.execute("INSERT INTO products (name, price, category) VALUES ('Laptop', 999.99, 'Electronics')")
    conn.execute("INSERT INTO products (name, price, category) VALUES ('Book', 19.99, 'Education')")
    conn.execute("INSERT INTO products (name, price, category) VALUES ('Phone', 699.99, 'Electronics')")
    conn.execute("INSERT INTO orders (user_id, product_id, quantity) VALUES (1, 1, 1)")
    conn.execute("INSERT INTO orders (user_id, product_id, quantity) VALUES (1, 2, 3)")
    conn.execute("INSERT INTO orders (user_id, product_id, quantity) VALUES (2, 3, 1)")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def in_memory_engine():
    """Create an in-memory SQLite engine with sample data."""
    import sqlite3
    engine = SQLiteEngine(path=":memory:", read_only=False)

    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            age INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL
        )
    """)
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@test.com', 25)")
    conn.execute("INSERT INTO products VALUES (1, 'Laptop', 999.99)")
    conn.execute("INSERT INTO products VALUES (2, 'Book', 19.99)")
    conn.execute("INSERT INTO orders VALUES (1, 1, 1)")
    conn.execute("INSERT INTO orders VALUES (2, 1, 2)")
    conn.execute("INSERT INTO orders VALUES (3, 2, 1)")
    conn.commit()
    conn.close()
    return engine


@pytest.fixture
def sample_config():
    return DatabaseConfig(
        url="sqlite:///:memory:",
        read_only=True,
        max_rows=100,
        max_output_bytes=50000,
    )
