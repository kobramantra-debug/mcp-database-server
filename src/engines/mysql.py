"""MySQL engine — optional dependency: pymysql>=1.1.0."""

import time
from src.engines.base import (
    BaseEngine, DBInfo, ColumnInfo, TableInfo, TableDetail,
    IndexInfo, ForeignKeyInfo, TableStats, QueryResult,
)


class MySQLEngine(BaseEngine):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        database: str = "mysql",
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
            import pymysql
        except ImportError:
            raise RuntimeError(
                "MySQL engine requires pymysql. "
                "Install with: pip install 'mcp-database-universal[mysql]'"
            )
        self._conn = pymysql.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            cursorclass=pymysql.cursors.DictCursor,
        )

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
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()["VERSION()"]
        return DBInfo(engine="mysql", version=version, name=self.database, size_approx="unknown")

    async def get_tables(self) -> list[TableInfo]:
        conn = self._ensure_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME, TABLE_ROWS
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """, [self.database])
            rows = cur.fetchall()

        tables = []
        for row in rows:
            tables.append(TableInfo(
                name=row["TABLE_NAME"],
                row_count=row.get("TABLE_ROWS", 0) or 0,
            ))
        return tables

    async def get_table_detail(self, table: str) -> TableDetail:
        conn = self._ensure_conn()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       COLUMN_KEY
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, [self.database, table])
            col_rows = cur.fetchall()

        columns = []
        pk_name = None
        for c in col_rows:
            is_pk = c["COLUMN_KEY"] == "PRI"
            if is_pk:
                pk_name = c["COLUMN_NAME"]
            columns.append(ColumnInfo(
                name=c["COLUMN_NAME"],
                type=c["DATA_TYPE"],
                nullable=(c["IS_NULLABLE"] == "YES"),
                default=str(c["COLUMN_DEFAULT"]) if c["COLUMN_DEFAULT"] is not None else None,
                is_primary_key=is_pk,
                is_foreign_key=(c["COLUMN_KEY"] == "MUL"),
            ))

        foreign_keys = []
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                      AND REFERENCED_TABLE_NAME IS NOT NULL
                """, [self.database, table])
                fk_rows = cur.fetchall()
            for fk in fk_rows:
                foreign_keys.append(ForeignKeyInfo(
                    column=fk["COLUMN_NAME"],
                    references_table=fk["REFERENCED_TABLE_NAME"],
                    references_column=fk["REFERENCED_COLUMN_NAME"],
                ))
        except Exception:
            pass

        stats = await self.get_table_stats(table)

        return TableDetail(
            name=table,
            columns=columns,
            foreign_keys=foreign_keys,
            primary_key=pk_name,
            stats=stats,
        )

    async def execute_query(self, sql: str, params: dict | None = None) -> QueryResult:
        conn = self._ensure_conn()
        start = time.monotonic()
        try:
            with conn.cursor() as cur:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description] if cur.description else []
                elapsed = int((time.monotonic() - start) * 1000)
                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=False,
                    execution_time_ms=elapsed,
                    sql=sql,
                )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return QueryResult(sql=sql, execution_time_ms=elapsed, warning=f"Error: {str(e)}")

    async def get_sample_data(self, table: str, limit: int = 5) -> QueryResult:
        return await self.execute_query(f'SELECT * FROM `{table}` LIMIT {limit}')

    async def get_table_stats(self, table: str) -> TableStats:
        return TableStats(row_count=0, total_size="unknown")

    def is_read_only(self) -> bool:
        return self._read_only
