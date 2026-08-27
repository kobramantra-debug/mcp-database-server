"""Create a small SQLite sample database for demonstrating mcp-database-universal."""

import pathlib
import sqlite3

DB_PATH = pathlib.Path(__file__).resolve().parent / "sample.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    age INTEGER
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    price REAL NOT NULL,
    stock INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1,
    created_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
"""

USERS = [
    (1, "Alice", "alice@example.com", 30),
    (2, "Bob", "bob@example.com", 25),
    (3, "Carol", "carol@example.com", 40),
    (4, "Dave", "dave@example.com", 19),
]

PRODUCTS = [
    (1, "Laptop", "computers", 999.0, 15),
    (2, "Mouse", "accessories", 29.0, 120),
    (3, "Keyboard", "accessories", 79.0, 60),
    (4, "Monitor", "computers", 299.0, 30),
    (5, "Headphones", "audio", 129.0, 45),
]

ORDERS = [
    (1, 1, 1, 1, "2026-01-10"),
    (2, 1, 2, 2, "2026-01-12"),
    (3, 2, 3, 1, "2026-01-14"),
    (4, 3, 4, 1, "2026-01-15"),
    (5, 4, 5, 3, "2026-01-16"),
    (6, 2, 1, 1, "2026-01-18"),
]


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)", USERS)
    conn.executemany("INSERT INTO products (id, name, category, price, stock) VALUES (?, ?, ?, ?, ?)", PRODUCTS)
    conn.executemany(
        "INSERT INTO orders (id, user_id, product_id, quantity, created_at) VALUES (?, ?, ?, ?, ?)",
        ORDERS,
    )
    conn.commit()
    conn.close()
    print(f"Created {DB_PATH}")


if __name__ == "__main__":
    main()