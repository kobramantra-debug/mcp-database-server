"""Safety layer for SQL query validation and enforcement."""

import re
from enum import Enum
from dataclasses import dataclass


class QueryType(Enum):
    SAFE_READ = "safe_read"
    UNSAFE_READ = "unsafe_read"
    WRITE = "write"
    DANGEROUS = "dangerous"
    UNKNOWN = "unknown"


@dataclass
class SafetyResult:
    approved: bool
    query_type: QueryType
    reason: str


SAFE_READ_PATTERNS = [
    re.compile(r"^\s*SELECT\b", re.IGNORECASE),
    re.compile(r"^\s*EXPLAIN\b", re.IGNORECASE),
    re.compile(r"^\s*PRAGMA\b", re.IGNORECASE),
    re.compile(r"^\s*SHOW\b", re.IGNORECASE),
    re.compile(r"^\s*DESCRIBE\b", re.IGNORECASE),
    re.compile(r"^\s*WITH\b.*\bSELECT\b", re.IGNORECASE | re.DOTALL),
]

WRITE_PATTERNS = [
    re.compile(r"^\s*INSERT\b", re.IGNORECASE),
    re.compile(r"^\s*UPDATE\b", re.IGNORECASE),
    re.compile(r"^\s*DELETE\b", re.IGNORECASE),
    re.compile(r"^\s*REPLACE\b", re.IGNORECASE),
    re.compile(r"^\s*MERGE\b", re.IGNORECASE),
]

DANGEROUS_PATTERNS = [
    re.compile(r"^\s*DROP\b", re.IGNORECASE),
    re.compile(r"^\s*ALTER\b", re.IGNORECASE),
    re.compile(r"^\s*CREATE\b", re.IGNORECASE),
    re.compile(r"^\s*TRUNCATE\b", re.IGNORECASE),
    re.compile(r"^\s*GRANT\b", re.IGNORECASE),
    re.compile(r"^\s*REVOKE\b", re.IGNORECASE),
]

SQL_INJECTION_PATTERNS = [
    re.compile(r"(?:--|#|/\*)", re.IGNORECASE),  # comments
    re.compile(r";\s*\w", re.IGNORECASE),         # multiple statements
    re.compile(r"'\s*OR\s+'", re.IGNORECASE),     # ' OR '1'='1
    re.compile(r"'\s*OR\s+\"", re.IGNORECASE),    # ' OR "1"="1
    re.compile(r"UNION\s+ALL\s+SELECT", re.IGNORECASE),
    re.compile(r"INTO\s+OUTFILE", re.IGNORECASE),
    re.compile(r"LOAD_FILE\s*\(", re.IGNORECASE),
    re.compile(r"BENCHMARK\s*\(", re.IGNORECASE),
    re.compile(r"SLEEP\s*\(", re.IGNORECASE),
    re.compile(r"WAITFOR\s+DELAY", re.IGNORECASE),
]


class SafetyValidator:
    def __init__(self, read_only: bool = True, max_rows: int = 1000, max_query_time: int = 30):
        self.read_only = read_only
        self.max_rows = max_rows
        self.max_query_time = max_query_time

    def classify(self, sql: str) -> QueryType:
        stripped = sql.strip()
        if not stripped:
            return QueryType.UNKNOWN

        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(stripped):
                return QueryType.DANGEROUS

        for pattern in WRITE_PATTERNS:
            if pattern.search(stripped):
                return QueryType.WRITE

        for pattern in SAFE_READ_PATTERNS:
            if pattern.search(stripped):
                return QueryType.SAFE_READ

        return QueryType.UNKNOWN

    def check_injection(self, sql: str) -> str | None:
        for pattern in SQL_INJECTION_PATTERNS:
            if pattern.search(sql):
                return f"Suspected SQL injection pattern detected"
        return None

    def validate(self, sql: str) -> SafetyResult:
        if not sql or not sql.strip():
            return SafetyResult(
                approved=False,
                query_type=QueryType.UNKNOWN,
                reason="Empty query",
            )

        injection = self.check_injection(sql)
        if injection:
            return SafetyResult(
                approved=False,
                query_type=QueryType.UNKNOWN,
                reason=injection,
            )

        qtype = self.classify(sql)

        if self.read_only and qtype in (QueryType.WRITE, QueryType.DANGEROUS):
            return SafetyResult(
                approved=False,
                query_type=qtype,
                reason=f"Query type '{qtype.value}' is not allowed in read-only mode. "
                       f"Set DATABASE_WRITE_ENABLED=true to allow write operations.",
            )

        if qtype == QueryType.UNKNOWN:
            return SafetyResult(
                approved=False,
                query_type=qtype,
                reason=f"Unrecognized query type. Only SELECT, EXPLAIN, PRAGMA, SHOW, DESCRIBE are allowed.",
            )

        if qtype == QueryType.UNSAFE_READ:
            return SafetyResult(
                approved=True,
                query_type=qtype,
                reason="Query approved with warning: contains potentially unsafe read operations",
            )

        return SafetyResult(
            approved=True,
            query_type=qtype,
            reason="Query approved",
        )

    def ensure_limit(self, sql: str) -> str:
        if self.max_rows <= 0:
            return sql
        stripped = sql.strip().rstrip(";")
        lower = stripped.lower()
        if "limit " in lower or "top " in lower:
            return sql
        if lower.startswith("select"):
            return f"{stripped} LIMIT {self.max_rows}"
        return sql
