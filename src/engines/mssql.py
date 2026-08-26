"""MSSQL engine — optional dependency: pyodbc>=5.1.0."""

import time
from src.engines.base import (
    BaseEngine, DBInfo, ColumnInfo, TableInfo, TableDetail,
    IndexInfo, ForeignKeyInfo, TableStats, QueryResult,
)


class MSSQLEngine(BaseEngine):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 1433,
        database: str = "master",
        user: str = "",
        password: str = "",
        read_only: bool = True,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self._read_only = read_only
        self._conn = None

    async def connect(self) -> None:
        try:
            import pyodbc
        except ImportError:
            raise RuntimeError(
                "MSSQL engine requires pyodbc. "
                "Install with: pip install 'mcp-database-server[mssql]'"
            )
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.host},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.user};"
            f"PWD={self.password};"
            f"TrustServerCertificate=yes;"
        )
        self._conn = pyodbc.connect(conn_str)

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_conn(self):
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._conn

    async def get_db_info(self) -> DBInfo:
        conn = self._ensure_conn()
        cur = conn.cursor()
        cur.execute("SELECT @@VERSION")
        version = cur.fetchone()[0].split("\n")[0] if cur.fetchone() else "unknown"
        return DBInfo(engine="mssql", version=version, name=self.database, size_approx="unknown")

    async def get_tables(self) -> list[TableInfo]:
        conn = self._ensure_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.name AS table_name, p.rows AS row_count
            FROM sys.tables t
            JOIN sys.partitions p ON t.object_id = p.object_id
            WHERE p.index_id IN (0, 1)
            ORDER BY t.name
        """)
        tables = []
        for row in cur.fetchall():
            tables.append(TableInfo(name=row[0], row_count=row[1]))
        return tables

    async def get_table_detail(self, table: str) -> TableDetail:
        conn = self._ensure_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT c.name AS column_name, tp.name AS type_name,
                   c.is_nullable, c.is_identity
            FROM sys.columns c
            JOIN sys.types tp ON c.user_type_id = tp.user_type_id
            JOIN sys.tables t ON c.object_id = t.object_id
            WHERE t.name = ?
            ORDER BY c.column_id
        """, [table])
        col_rows = cur.fetchall()

        columns = []
        for c in col_rows:
            columns.append(ColumnInfo(
                name=c[0],
                type=c[1],
                nullable=bool(c[2]),
                is_primary_key=bool(c[3]),
            ))

        foreign_keys = []
        try:
            cur.execute("""
                SELECT
                    fc.name AS column_name,
                    OBJECT_NAME(fk.referenced_object_id) AS ref_table,
                    rc.name AS ref_column
                FROM sys.foreign_keys fk
                JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
                JOIN sys.columns fc ON fkc.parent_object_id = fc.object_id AND fkc.parent_column_id = fc.column_id
                JOIN sys.columns rc ON fkc.referenced_object_id = rc.object_id AND fkc.referenced_column_id = rc.column_id
                WHERE OBJECT_NAME(fk.parent_object_id) = ?
            """, [table])
            for fk in cur.fetchall():
                foreign_keys.append(ForeignKeyInfo(
                    column=fk[0],
                    references_table=fk[1],
                    references_column=fk[2],
                ))
        except Exception:
            pass

        stats = await self.get_table_stats(table)

        return TableDetail(
            name=table,
            columns=columns,
            foreign_keys=foreign_keys,
            stats=stats,
        )

    async def execute_query(self, sql: str, params: dict | None = None) -> QueryResult:
        conn = self._ensure_conn()
        start = time.monotonic()
        try:
            cur = conn.cursor()
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description] if cur.description else []
            elapsed = int((time.monotonic() - start) * 1000)
            return QueryResult(
                columns=columns,
                rows=[dict(zip(columns, row)) for row in rows],
                row_count=len(rows),
                truncated=False,
                execution_time_ms=elapsed,
                sql=sql,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return QueryResult(sql=sql, execution_time_ms=elapsed, warning=f"Error: {str(e)}")

    async def get_sample_data(self, table: str, limit: int = 5) -> QueryResult:
        return await self.execute_query(f"SELECT TOP {limit} * FROM [{table}]")

    async def get_table_stats(self, table: str) -> TableStats:
        return TableStats(row_count=0, total_size="unknown")

    def is_read_only(self) -> bool:
        return self._read_only
