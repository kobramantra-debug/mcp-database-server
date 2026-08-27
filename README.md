# MCP Database Server

Reasoning interface for databases — not a thin wrapper.

## Features

- **7 reasoning tools** for AI agents to work with databases
- **Multi-engine**: SQLite (built-in), PostgreSQL, MySQL, MSSQL (optional)
- **Safety first**: read-only default, parameterized queries, injection prevention
- **LLM-friendly output**: types translated, NULLs handled, results contextualized
- **Schema introspection**: auto-discover tables, columns, relationships, indexes
- **Natural language queries**: ask questions in plain text, get SQL + results

## Install

```bash
pip install mcp-database-universal

# With optional engines:
pip install "mcp-database-server[postgres]"
pip install "mcp-database-server[mysql]"
pip install "mcp-database-server[mssql]"
```

## Usage

```bash
DATABASE_URL=sqlite:///mydb.db python -m mcp_database_universal
```

## Docker

```bash
docker build -t mcp-db .
docker run --rm -i -e DATABASE_URL=sqlite:///:memory: mcp-db
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (required) | Connection URL |
| `DATABASE_READ_ONLY` | `true` | Read-only mode |
| `DATABASE_MAX_ROWS` | `1000` | Max rows per query |
| `DATABASE_MAX_QUERY_TIME` | `30` | Query timeout (seconds) |

## License

MIT
