# Examples

This directory contains ready-to-use snippets for wiring `mcp-database-universal` into common MCP clients, plus a small script that builds a sample database you can point the server at.

## Build a sample database

```bash
python examples/create_sample_db.py
```

This creates `examples/sample.db` (SQLite) with three related tables: `users`, `products`, and `orders`.

## Run the server against the sample database

```bash
DATABASE_URL=sqlite:///examples/sample.db python -m mcp_database_universal
```

## Client configuration

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "database": {
      "command": "python",
      "args": ["-m", "mcp_database_universal"],
      "env": {
        "DATABASE_URL": "sqlite:///C:/path/to/examples/sample.db"
      }
    }
  }
}
```

### OpenCode (`opencode.json`)

```json
{
  "mcp": {
    "database": {
      "type": "stdio",
      "command": ["python", "-m", "mcp_database_universal"],
      "env": {
        "DATABASE_URL": "sqlite:///C:/path/to/examples/sample.db"
      }
    }
  }
}
```

### Cursor (`mcp.json`)

```json
{
  "mcpServers": {
    "database": {
      "command": "uvx",
      "args": ["mcp-database-universal"],
      "env": {
        "DATABASE_URL": "sqlite:///C:/path/to/examples/sample.db"
      }
    }
  }
}
```

> Replace `C:/path/to/examples/sample.db` with the absolute path to your database on your platform.

## Postgres / MySQL / MSSQL

For a server-backed database, use the appropriate URL and install the matching extra:

```bash
pip install "mcp-database-universal[postgres]"
DATABASE_URL=postgresql://user:pass@host:5432/mydb python -m mcp_database_universal
```

```bash
DATABASE_URL=mysql://user:pass@host:3306/mydb python -m mcp_database_universal
```

```bash
DATABASE_URL=mssql://user:pass@host:1433/mydb python -m mcp_database_universal
```