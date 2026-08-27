"""Abstract base class for database engines."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DBInfo:
    engine: str
    version: str
    name: str
    size_approx: str


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_table: str | None = None
    foreign_key_column: str | None = None


@dataclass
class TableInfo:
    name: str
    row_count: int = 0
    column_count: int = 0
    has_primary_key: bool = False
    foreign_keys_out: int = 0
    foreign_keys_in: int = 0


@dataclass
class IndexInfo:
    name: str
    columns: list[str] = field(default_factory=list)
    unique: bool = False


@dataclass
class ForeignKeyInfo:
    column: str = ""
    references_table: str = ""
    references_column: str = ""


@dataclass
class TableStats:
    row_count: int = 0
    avg_row_size: str = "unknown"
    total_size: str = "unknown"
    null_counts: dict[str, int] = field(default_factory=dict)
    value_distribution: dict[str, dict] = field(default_factory=dict)


@dataclass
class TableDetail:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    indexes: list[IndexInfo] = field(default_factory=list)
    primary_key: str | None = None
    foreign_keys: list[ForeignKeyInfo] = field(default_factory=list)
    sample_data: list[dict] = field(default_factory=list)
    stats: TableStats = field(default_factory=TableStats)


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    execution_time_ms: int = 0
    sql: str = ""
    warning: str | None = None


_NAMED_PARAM_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def _named_to_pyformat(sql: str) -> str:
    """Convert :name named params (SQLite style) to %(name)s (DBAPI pyformat style).

    Used by psycopg (PostgreSQL), pymysql (MySQL) and MSSQL drivers,
    which do not understand the :name syntax.
    """
    return _NAMED_PARAM_RE.sub(r"%(\1)s", sql)


class BaseEngine(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    def _translate_params(self, sql: str, params: dict | None) -> tuple[str, dict | None]:
        """Normalize :name params to the driver-native style when params are given."""
        if params:
            sql = _named_to_pyformat(sql)
        return sql, params

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_db_info(self) -> DBInfo: ...

    @abstractmethod
    async def get_tables(self) -> list[TableInfo]: ...

    @abstractmethod
    async def get_table_detail(self, table: str) -> TableDetail: ...

    @abstractmethod
    async def execute_query(self, sql: str, params: dict | None = None) -> QueryResult: ...

    @abstractmethod
    async def get_sample_data(self, table: str, limit: int = 5) -> QueryResult: ...

    @abstractmethod
    async def get_table_stats(self, table: str) -> TableStats: ...

    @abstractmethod
    def is_read_only(self) -> bool: ...
