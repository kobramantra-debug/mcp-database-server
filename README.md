# MCP Database Server

A reasoning interface for databases for MCP-capable AI agents — not a thin SQL wrapper.

`mcp-database-universal` gives AI agents a set of **7 reasoning tools** to explore and query a database safely, understand its schema and data shape, run natural-language questions, and visualize relationships — all without exposing raw connection internals.

## Features

- **7 reasoning tools** designed for AI agents: test connection, list tables, inspect a table, run parameterized SQL, ask questions in plain language, profile data, and render an ER diagram.
- **Multi-engine**: SQLite (built-in) plus optional PostgreSQL, MySQL, and MSSQL.
- **Safety first**: read-only by default, parameterized queries, statement validation, row/time/output limits.
- **LLM-friendly output**: types translated, `NULL`s handled, results formatted in Markdown tables with context.
- **Schema introspection**: auto-discover tables, columns, indexes, foreign keys, and relationships.
- **Natural language queries**: translate plain-text questions into SQL and return results.

## Supported engines

| Engine      | Requirement    | Install extra                    |
|-------------|----------------|----------------------------------|
| SQLite      | built-in       | —                                |
| PostgreSQL  | psycopg        | `pip install "mcp-database-universal[postgres]"` |
| MySQL       | PyMySQL        | `pip install "mcp-database-universal[mysql]"`     |
| MSSQL       | pyodbc + ODBC driver | `pip install "mcp-database-universal[mssql]"`     |
| all         | —              | `pip install "mcp-database-universal[all]"`       |

## Install

```bash
pip install mcp-database-universal

# With optional engines:
pip install "mcp-database-universal[postgres]"
pip install "mcp-database-universal[mysql]"
pip install "mcp-database-universal[mssql]"
# or everything:
pip install "mcp-database-universal[all]"
```

## Quick start

Run the server over STDIO (the default transport for MCP clients):

```bash
DATABASE_URL=sqlite:///app.db python -m mcp_database_universal
```

Connection URLs:

```
sqlite:///path/to/db.db              SQLite (file)
sqlite:///:memory:                   SQLite (in-memory)
postgresql://user:pass@host:5432/db  PostgreSQL
mysql://user:pass@host:3306/db       MySQL
mssql://user:pass@host:1433/db       MSSQL (uses ODBC Driver 18)
```

## Docker

```bash
docker build -t mcp-db .

# Mount a SQLite database read-only:
docker run --rm -i \
  -v /host/path/app.db:/data/app.db:ro \
  -e DATABASE_URL=sqlite:////data/app.db \
  mcp-db

# Or in-memory:
docker run --rm -i -e DATABASE_URL=sqlite:///:memory: mcp-db
```

## Configuration

All configuration is done through environment variables.

| Variable                    | Default   | Description                                            |
|-----------------------------|-----------|--------------------------------------------------------|
| `DATABASE_URL`              | *(required)* | Database connection URL.                            |
| `DATABASE_READ_ONLY`        | `true`    | Enforce read-only mode (blocks writes even if `DATABASE_WRITE_ENABLED`). |
| `DATABASE_WRITE_ENABLED`    | `false`   | Allow write statements when `DATABASE_READ_ONLY=false`. |
| `DATABASE_MAX_ROWS`         | `1000`    | Maximum rows returned per query.                       |
| `DATABASE_MAX_QUERY_TIME`   | `30`      | Query timeout in seconds.                              |
| `DATABASE_MAX_OUTPUT_BYTES` | `50000`   | Cap on result payload size.                            |
| `DATABASE_SAMPLE_SIZE`      | `5`       | Number of sample rows shown in table/column stats.     |
| `DATABASE_PROFILE_TOP_N`    | `10`      | Top-N value distribution entries in profiling.         |
| `OPENAI_API_KEY`            | —         | API key for the LLM-backed `natural_query` (OpenAI).            |
| `ANTHROPIC_API_KEY`         | —         | API key for the LLM-backed `natural_query` (Anthropic).         |

## Tools

| Tool               | Description                                                        |
|--------------------|--------------------------------------------------------------------|
| `test_connection`  | Test DB connectivity; report engine, version, name, size, table count. |
| `list_tables`      | Overview of all tables with row counts, column counts, FK relationships. |
| `inspect_table`    | Full structure of one table: columns, types, indexes, FKs, sample data. |
| `query`            | Run a safe, parameterized SQL query and get Markdown results.      |
| `natural_query`    | Ask a question in plain text; get generated SQL + results.         |
| `profile_database` | Data profile: distributions, NULL rates, relationships, sizes.     |
| `schema_graph`     | Mermaid ER diagram of table relationships.                         |

### Example: `query` with parameters

```json
{
  "sql": "SELECT * FROM users WHERE id = :id AND active = :active",
  "params": "{\"id\": 42, \"active\": true}"
}
```

Parameters use `:name` placeholders; pass the values as a JSON string in `params`.

### Example: `natural_query`

```text
question: "How many users are there?"
-> SELECT COUNT(*) FROM users
question: "Show me all orders"
-> SELECT * FROM orders LIMIT 100
```

How the question is translated:

- If `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) is set, the question is sent to
  an LLM that returns a single read-only SQL statement. The result always
  passes through the safety validator before execution.
- Otherwise a built-in rules-based parser handles common English question
  shapes ("how many X", "show me X", "top N <column> in X", "X where column = value").
  It matches table names against the database's real schema.

A working example against a small sample database is in [`examples/`](examples/) together with ready-to-use configuration snippets for common MCP clients.

## MCP client configuration

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "database": {
      "command": "python",
      "args": ["-m", "mcp_database_universal"],
      "env": {"DATABASE_URL": "sqlite:///C:/data/app.db"}
    }
  }
}
```

### Cursor / other CLI-based clients

```json
{
  "mcpServers": {
    "database": {
      "command": "uvx",
      "args": ["mcp-database-universal"],
      "env": {"DATABASE_URL": "sqlite:///C:/data/app.db"}
    }
  }
}
```

> **Windows note**: the async Postgres driver requires the Windows selector event loop. The package sets this policy automatically on `win32`, so no extra configuration is needed.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Integration tests for PostgreSQL/MySQL use Docker Compose and are skipped automatically if the servers are unreachable:

```bash
docker compose -f tests/integration/docker-compose.yml up -d
pytest
```

## Safety model

- The server is **read-only by default**; `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER` and other write statements are blocked.
- Writes are only possible when the operator explicitly sets `DATABASE_READ_ONLY=false` **and** `DATABASE_WRITE_ENABLED=true`.
- Query results are capped by row count, timeout, and output size — runaway queries are prevented.

## License

MIT