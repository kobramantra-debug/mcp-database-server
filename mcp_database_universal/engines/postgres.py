"""PostgreSQL engine — optional dependency: psycopg[binary]>=3.1.0."""

import time
from mcp_database_universal.engines.base import (
    BaseEngine, DBInfo, ColumnInfo, TableInfo, TableDetail,
    IndexInfo, ForeignKeyInfo, TableStats, QueryResult,
    _named_to_pyformat,
)


class PostgresEngine(BaseEngine):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
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
            import psycopg
        except ImportError:
            raise RuntimeError(
                "PostgreSQL engine requires psycopg. "
                "Install with: pip install 'mcp-database-universal[postgres]'"
            )
        self._conn = await psycopg.AsyncConnection.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            autocommit=True,
        )

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _ensure_conn(self):
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._conn

    async def get_db_info(self) -> DBInfo:
        conn = self._ensure_conn()
        cur = await conn.execute("SELECT version()")
        row = await cur.fetchone()
        version = row[0] if row else "unknown"
        try:
            cur = await conn.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            )
            row2 = await cur.fetchone()
            size = row2[0] if row2 else "unknown"
        except Exception:
            size = "unknown"
        return DBInfo(engine="postgresql", version=version, name=self.database, size_approx=size)

    async def get_tables(self) -> list[TableInfo]:
        conn = self._ensure_conn()
        cur = await conn.execute("""
            SELECT t.table_name
            FROM information_schema.tables t
            WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_name
        """)
        rows = await cur.fetchall()

        tables = []
        for row in rows:
            name = row[0]
            try:
                cur = await conn.execute(f'SELECT COUNT(*) FROM "{name}"')
                cnt = await cur.fetchone()
                row_count = cnt[0] if cnt else 0
            except Exception:
                row_count = 0

            try:
                cur = await conn.execute("""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                """, [name])
                cols = await cur.fetchone()
                col_count = cols[0] if cols else 0
            except Exception:
                col_count = 0

            tables.append(TableInfo(
                name=name,
                row_count=row_count,
                column_count=col_count,
            ))

        return tables

    async def get_table_detail(self, table: str) -> TableDetail:
        conn = self._ensure_conn()

        cur = await conn.execute("""
            SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
                   CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_pk
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_schema = 'public' AND c.table_name = %s
            ORDER BY c.ordinal_position
        """, [table, table])
        col_rows = await cur.fetchall()

        columns = []
        pk_name = None
        for c in col_rows:
            is_pk = c[4]
            if is_pk:
                pk_name = c[0]
            columns.append(ColumnInfo(
                name=c[0],
                type=c[1],
                nullable=(c[2] == "YES"),
                default=c[3],
                is_primary_key=is_pk,
            ))

        cur = await conn.execute("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = %s
        """, [table])
        fk_rows = await cur.fetchall()

        foreign_keys = []
        fk_cols = set()
        for fk in fk_rows:
            foreign_keys.append(ForeignKeyInfo(
                column=fk[0],
                references_table=fk[1],
                references_column=fk[2],
            ))
            fk_cols.add(fk[0])

        for col in columns:
            if col.name in fk_cols:
                col.is_foreign_key = True
                for fk in foreign_keys:
                    if fk.column == col.name:
                        col.foreign_key_table = fk.references_table
                        col.foreign_key_column = fk.references_column
                        break

        cur = await conn.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = %s AND schemaname = 'public'
        """, [table])
        idx_rows = await cur.fetchall()

        indexes = []
        for idx in idx_rows:
            name = idx[0]
            unique = "UNIQUE" in (idx[1] or "").upper()
            indexes.append(IndexInfo(name=name, columns=[], unique=unique))

        try:
            cur = await conn.execute(f'SELECT * FROM "{table}" LIMIT 5')
            sample_rows = await cur.fetchall()
            if sample_rows:
                cols_d = [d.name for d in cur.description] if cur.description else []
                sample_data = [dict(zip(cols_d, row)) for row in sample_rows]
            else:
                sample_data = []
        except Exception:
            sample_data = []

        stats = await self.get_table_stats(table)

        return TableDetail(
            name=table,
            columns=columns,
            indexes=indexes,
            primary_key=pk_name,
            foreign_keys=foreign_keys,
            sample_data=sample_data,
            stats=stats,
        )

    async def execute_query(self, sql: str, params: dict | None = None) -> QueryResult:
        conn = self._ensure_conn()
        start = time.monotonic()
        try:
            sql, params = self._translate_params(sql, params)
            if params:
                cur = await conn.execute(sql, params)
            else:
                cur = await conn.execute(sql)
            rows = await cur.fetchall()
            columns = [desc.name for desc in cur.description] if cur.description else []
            elapsed = int((time.monotonic() - start) * 1000)
            result_rows = [dict(zip(columns, row)) for row in rows]
            return QueryResult(
                columns=columns,
                rows=result_rows,
                row_count=len(result_rows),
                truncated=False,
                execution_time_ms=elapsed,
                sql=sql,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return QueryResult(
                sql=sql,
                execution_time_ms=elapsed,
                warning=f"Error: {str(e)}",
            )

    async def get_sample_data(self, table: str, limit: int = 5) -> QueryResult:
        return await self.execute_query(f'SELECT * FROM "{table}" LIMIT {limit}')

    async def get_table_stats(self, table: str) -> TableStats:
        conn = self._ensure_conn()
        try:
            cur = await conn.execute(f'SELECT COUNT(*) FROM "{table}"')
            row = await cur.fetchone()
            row_count = row[0] if row else 0
        except Exception:
            row_count = 0

        try:
            cur = await conn.execute(
                "SELECT pg_size_pretty(pg_total_relation_size(%s))", [table]
            )
            row = await cur.fetchone()
            total_size = row[0] if row else "unknown"
        except Exception:
            total_size = "unknown"

        return TableStats(
            row_count=row_count,
            total_size=total_size,
        )

    def is_read_only(self) -> bool:
        return self._read_only
