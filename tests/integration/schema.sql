CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    age INTEGER
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price INTEGER
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1,
    created_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

INSERT INTO users (id, name, email, age) VALUES
    (1, 'Alice', 'alice@example.com', 30),
    (2, 'Bob', 'bob@example.com', 25),
    (3, 'Carol', 'carol@example.com', 40);

INSERT INTO products (id, name, price) VALUES
    (1, 'Laptop', 500),
    (2, 'Mouse', 20),
    (3, 'Keyboard', 50);

INSERT INTO orders (id, user_id, product_id, quantity) VALUES
    (1, 1, 1, 1),
    (2, 1, 2, 2),
    (3, 2, 3, 1),
    (4, 3, 1, 1);