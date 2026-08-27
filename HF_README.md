---
language:
  - en
tags:
  - mcp
  - model-context-protocol
  - ai-tools
  - database
  - sqlite
  - postgresql
  - mysql
  - mssql
library_name: mcp-database-universal
license: mit
---

# MCP Database Universal

A reasoning interface for databases — not a thin execution wrapper. Designed so LLM agents understand *what* the data means, not just how to fetch it.

## What it does

- **7 tools** designed for agent thinking: `test_connection`, `list_tables`, `inspect_table`, `query`, `natural_query`, `profile_database`, `schema_graph`
- **4 database engines**: SQLite (built-in), PostgreSQL, MySQL, MSSQL (optional extras)
- **Read-only by default** — write operations only with `DATABASE_WRITE_ENABLED=true`
- **Safety layer** — SQL injection detection, read-only classification, LIMIT enforcement, 30s timeout, 1000-row limit
- **LLM formatter** — type translation (e.g. `VARCHAR(255)` → "text, max 255 chars"), NULL → `(empty)`, truncation to 50KB
- **Schema inspector** — relationship discovery + Mermaid ER diagram generation
- **Zero-config SQLite** via `DATABASE_URL=sqlite:///path/to.db`

## Installation

```bash
pip install mcp-database-universal
pip install "mcp-database-universal[postgres]"   # PostgreSQL support
pip install "mcp-database-universal[mysql]"      # MySQL support
pip install "mcp-database-universal[mssql]"      # MSSQL support
```

## Quick Start

### Run locally
```bash
python -m mcp_database_universal
```

### Run with Docker
```bash
docker run -i -e DATABASE_URL=sqlite:////data/app.db \
  -v ./data:/data mcp-database-universal:latest
```

## Configuration (env vars)

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | `sqlite:///path.db`, `postgresql://...`, `mysql://...`, `mssql://...` | required |
| `DATABASE_WRITE_ENABLED` | Allow write operations (INSERT/UPDATE/DELETE) | `false` |
| `DATABASE_QUERY_LIMIT` | Max rows returned per query | `1000` |
| `DATABASE_TIMEOUT` | Query timeout in seconds | `30` |

## Tools

| Tool | Description |
|------|-------------|
| `test_connection` | Verify connection, get engine type, version, size |
| `list_tables` | Overview of tables with row counts and relationships |
| `inspect_table` | Full table structure: columns, types, keys, sample data |
| `query` | Execute parametrized, safety-checked SQL |
| `natural_query` | Ask in plain language, get SQL + results + explanation |
| `profile_database` | Value distributions, NULL rates, relationships, sizes |
| `schema_graph` | Mermaid ER diagram of relationships |

## License

MIT