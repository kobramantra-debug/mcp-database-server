"""SQLite engine — built-in, no external dependencies."""

import sqlite3
import os
import time
from mcp_database_universal.engines.base import (
    BaseEngine, DBInfo, ColumnInfo, TableInfo, TableDetail,
    IndexInfo, ForeignKeyInfo, TableStats, QueryResult,
)


class SQLiteEngine(BaseEngine):
    def __init__(self, path: str = ":memory:", read_only: bool = True):
        self.path = path
        self._read_only = read_only
        self._conn: sqlite3.Connection | None = None

    async def connect(self) -> None:
        if self.path == ":memory:":
            self._conn = sqlite3.connect(":memory:")
        else:
            dir_path = os.path.dirname(self.path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            if self._read_only:
                uri = f"file:{self.path}?mode=ro"
                self._conn = sqlite3.connect(uri, uri=True)
            else:
                self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        if not self._read_only:
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass
        self._conn.execute("PRAGMA foreign_keys=ON")

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._conn

    async def get_db_info(self) -> DBInfo:
        conn = self._ensure_conn()
        version = conn.execute("SELECT sqlite_version()").fetchone()[0]
        if self.path == ":memory:":
            name = ":memory:"
            size = "~0 KB"
        else:
            name = self.path
            try:
                size_bytes = os.path.getsize(self.path)
                if size_bytes < 1024:
                    size = f"~{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size = f"~{size_bytes // 1024} KB"
                else:
                    size = f"~{size_bytes // (1024 * 1024)} MB"
            except OSError:
                size = "unknown"
        return DBInfo(engine="sqlite", version=version, name=name, size_approx=size)

    async def get_tables(self) -> list[TableInfo]:
        conn = self._ensure_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        tables = []
        for row in rows:
            name = row["name"]
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except Exception:
                count = 0

            try:
                cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
                col_count = len(cols)
                has_pk = any(c["pk"] for c in cols)
            except Exception:
                col_count = 0
                has_pk = False

            try:
                fks = conn.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()
                fk_out = len(fks)
            except Exception:
                fk_out = 0

            tables.append(TableInfo(
                name=name,
                row_count=count,
                column_count=col_count,
                has_primary_key=has_pk,
                foreign_keys_out=fk_out,
                foreign_keys_in=0,
            ))

        for t in tables:
            for other in tables:
                if other.name == t.name:
                    continue
                try:
                    fks = conn.execute(f'PRAGMA foreign_key_list("{other.name}")').fetchall()
                    for fk in fks:
                        if fk["table"] == t.name:
                            t.foreign_keys_in += 1
                except Exception:
                    pass

        return tables

    async def get_table_detail(self, table: str) -> TableDetail:
        conn = self._ensure_conn()

        col_rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        columns = []
        pk_name = None
        for c in col_rows:
            is_pk = bool(c["pk"])
            if is_pk:
                pk_name = c["name"]
            columns.append(ColumnInfo(
                name=c["name"],
                type=c["type"] or "TEXT",
                nullable=not c["notnull"],
                default=c["dflt_value"],
                is_primary_key=is_pk,
            ))

        fk_rows = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
        foreign_keys = []
        fk_cols = set()
        for fk in fk_rows:
            foreign_keys.append(ForeignKeyInfo(
                column=fk["from"],
                references_table=fk["table"],
                references_column=fk["to"],
            ))
            fk_cols.add(fk["from"])

        for col in columns:
            if col.name in fk_cols:
                col.is_foreign_key = True
                for fk in foreign_keys:
                    if fk.column == col.name:
                        col.foreign_key_table = fk.references_table
                        col.foreign_key_column = fk.references_column
                        break

        idx_rows = conn.execute(f'PRAGMA index_list("{table}")').fetchall()
        indexes = []
        for idx in idx_rows:
            idx_info = conn.execute(f'PRAGMA index_info("{idx["name"]}")').fetchall()
            idx_cols = [i["name"] for i in idx_info]
            indexes.append(IndexInfo(
                name=idx["name"],
                columns=idx_cols,
                unique=bool(idx["unique"]),
            ))

        try:
            sample = conn.execute(f'SELECT * FROM "{table}" LIMIT 5').fetchall()
            sample_data = [dict(row) for row in sample]
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
            if params:
                cursor = conn.execute(sql, params)
            else:
                cursor = conn.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            elapsed = int((time.monotonic() - start) * 1000)
            result_rows = [dict(row) for row in rows]
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
        sql = f'SELECT * FROM "{table}" LIMIT {limit}'
        return await self.execute_query(sql)

    async def get_table_stats(self, table: str) -> TableStats:
        conn = self._ensure_conn()
        try:
            row_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        except Exception:
            row_count = 0

        try:
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            total_bytes = page_count * page_size
            if total_bytes < 1024:
                total_size = f"~{total_bytes} B"
            elif total_bytes < 1024 * 1024:
                total_size = f"~{total_bytes // 1024} KB"
            else:
                total_size = f"~{total_bytes // (1024 * 1024)} MB"
            avg_row_size = f"~{total_bytes // max(row_count, 1)} B" if row_count > 0 else "~0 B"
        except Exception:
            total_size = "unknown"
            avg_row_size = "unknown"

        null_counts: dict[str, int] = {}
        try:
            col_rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            for c in col_rows:
                try:
                    cnt = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE "{c["name"]}" IS NULL'
                    ).fetchone()[0]
                    if cnt > 0:
                        null_counts[c["name"]] = cnt
                except Exception:
                    pass
        except Exception:
            pass

        return TableStats(
            row_count=row_count,
            avg_row_size=avg_row_size,
            total_size=total_size,
            null_counts=null_counts,
        )

    def is_read_only(self) -> bool:
        return self._read_only
