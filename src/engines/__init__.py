"""Engine factory — auto-detect engine from DATABASE_URL."""

from urllib.parse import urlparse
from src.engines.base import BaseEngine


def get_engine(url: str, read_only: bool = True) -> BaseEngine:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme == "sqlite":
        from src.engines.sqlite import SQLiteEngine
        path = parsed.netloc + parsed.path
        if path == ":memory:" or path == "/:memory:":
            path = ":memory:"
        elif path.startswith("/") and len(path) > 1:
            path = path[1:]
        return SQLiteEngine(path=path, read_only=read_only)

    if scheme in ("postgresql", "postgres"):
        from src.engines.postgres import PostgresEngine
        return PostgresEngine(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            database=(parsed.path.lstrip("/") or "postgres"),
            user=parsed.username or "",
            password=parsed.password or "",
            read_only=read_only,
        )

    if scheme == "mysql":
        from src.engines.mysql import MySQLEngine
        return MySQLEngine(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            database=(parsed.path.lstrip("/") or "mysql"),
            user=parsed.username or "",
            password=parsed.password or "",
            read_only=read_only,
        )

    if scheme in ("mssql", "sqlserver"):
        from src.engines.mssql import MSSQLEngine
        return MSSQLEngine(
            host=parsed.hostname or "localhost",
            port=parsed.port or 1433,
            database=(parsed.path.lstrip("/") or "master"),
            user=parsed.username or "",
            password=parsed.password or "",
            read_only=read_only,
        )

    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme}")
