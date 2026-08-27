"""Entry point for MCP Database Server."""

import asyncio
import os
import sys
import logging
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp-db")


def _parse_url(url: str) -> tuple[str, dict]:
    """Parse DATABASE_URL into engine name and connection kwargs."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme == "sqlite":
        if parsed.path == ":memory:" or parsed.netloc + parsed.path == ":memory:":
            return "sqlite", {"path": ":memory:"}
        path = parsed.netloc + parsed.path
        if path.startswith("/") and len(path) > 1:
            path = path[1:]
        return "sqlite", {"path": path}

    if scheme in ("postgresql", "postgres"):
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        database = parsed.path.lstrip("/") or "postgres"
        user = parsed.username
        password = parsed.password
        return "postgresql", {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
        }

    if scheme == "mysql":
        host = parsed.hostname or "localhost"
        port = parsed.port or 3306
        database = parsed.path.lstrip("/") or "mysql"
        user = parsed.username
        password = parsed.password
        return "mysql", {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
        }

    if scheme in ("mssql", "sqlserver"):
        host = parsed.hostname or "localhost"
        port = parsed.port or 1433
        database = parsed.path.lstrip("/") or "master"
        user = parsed.username
        password = parsed.password
        return "mssql", {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
        }

    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme}")


async def main():
    from mcp_database_universal.config import DatabaseConfig
    from mcp_database_universal.engines import get_engine
    from mcp_database_universal.server import create_server

    config = DatabaseConfig.from_env()
    engine = get_engine(config.url)
    await engine.connect()

    server = await create_server(config, engine)

    logger.info("MCP Database Server starting (STDIO transport)")
    await server.run_stdio_async()


if __name__ == "__main__":
    if sys.platform == "win32":
        # psycopg async does not work with ProactorEventLoop (Windows default)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
