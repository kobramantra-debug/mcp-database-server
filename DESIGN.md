# MCP Database Server — Kompletní návrh

## 1. Problematika

### Co špatně dělají současné DB MCP servery
| Server | Stav | Problém |
|--------|------|---------|
| `server-postgres` (oficiální) | Archivovaný | SQL injection CVE |
| `server-sqlite` (oficiální) | Archivovaný | SQL injection CVE |
| `@bytebase/dbhub` | Aktivní | Read-only, bez contextu pro LLM |
| `@benborla29/mcp-server-postgres` | Aktivní | Jen PostgreSQL, bez safety layer |
| `sqlite-server` | Aktivní | Jen SQLite, základní |

### Jak uživatelé reálně používají DB přes MCP
```
# ŠPATNĚ (12+ volání na jednoduchý úkol):
1. list_tables()
2. inspect_table("users")
3. inspect_table("orders")
4. inspect_table("products")
5. query("SELECT * FROM users LIMIT 5")
6. query("SELECT * FROM orders LIMIT 5")
7. query("SELECT * FROM products LIMIT 5")
8. query("SELECT u.name, COUNT(o.id) FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.name")
9. query("SELECT p.name, SUM(oi.quantity) FROM products p JOIN order_items oi ON p.id = oi.product_id GROUP BY p.name")
10. query("SELECT DATE(created_at), COUNT(*) FROM orders GROUP BY DATE(created_at)")
11. Ručně interpretovat 11 výsledků
12. Spojit je dohromady

# SPRÁVNĚ (2 volání):
1. profile_database()  → kompletní přehled, vztahy, distribuce
2. natural_query("Jaký produkt se nejvíce prodává a kolik má objednávek?")  → SQL + výsledky + kontext
```

---

## 2. Designové principy

### P1: Reasoning Interface, ne Execution Wrapper
Špatný přístup: "Tady je `execute_sql()` — pošli mi SQL."
Správný přístup: "Tady je `natural_query()` — napiš mi co chceš vědět, já se postarám o SQL, bezpečnost a formátování."

### P2: Méně nástrojů = lepší výsledky
LLM modely mají omezený kontext. Každý nástroj = popis + schema + příklady v system promptu.
**Maximum 8 nástrojů.** Žádný redundantní.

### P3: Safety First
- Read-only default (žádný zápis bez explicitního povolení)
- Parametrizované dotazy (žádný string formatting)
- Query timeout (30s default)
- Row limit (1000 default)
- Výstupní truncation (50KB pro LLM kontext)

### P4: LLM-Friendly Output
- Technické typy → popisné názvy
- NULL hodnoty → "(empty)"
- Čísla → formátovaná (1,234,567)
- Datumy → ISO 8601
- Výsledky + kontext (počet řádků, čas dotazu, varování)

### P5: Multi-Engine Abstraction
Stejné nástroje, stejný výstup, ať používáš cokoliv. Engine se pozná z connection stringu.

---

## 3. Architektura

```
mcp-db/
├── src/
│   ├── __init__.py
│   ├── __main__.py              # python -m mcp_database_universal
│   ├── server.py                # MCPServer — registrace nástrojů
│   ├── config.py                # Načtení env var, validace
│   ├── safety.py                # SQL validation, write detection, limity
│   ├── schema_inspector.py      # Schema introspection, FK discovery
│   ├── engines/
│   │   ├── __init__.py          # get_engine(url) → Engine
│   │   ├── base.py              # Abstract BaseEngine
│   │   ├── sqlite.py            # SQLite (built-in)
│   │   ├── postgres.py          # PostgreSQL (optional: psycopg)
│   │   ├── mysql.py             # MySQL (optional: pymysql)
│   │   └── mssql.py             # MSSQL (optional: pyodbc)
│   └── formatters/
│       ├── __init__.py
│       └── llm.py               # LLM-friendly output formatting
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures, in-memory SQLite
│   ├── test_engines.py          # Engine unit tests
│   ├── test_safety.py           # Safety layer tests
│   ├── test_schema.py           # Schema inspector tests
│   ├── test_formatter.py        # LLM formatter tests
│   ├── test_server.py           # MCP tool integration tests
│   └── test_stdio.py            # Docker STDIO handshake
├── Dockerfile
├── pyproject.toml
├── .env.example
├── LICENSE (MIT)
├── README.md
└── .github/
    └── workflows/
        ├── ci.yml
        └── publish.yml
```

---

## 4. Engines — Detailní návrh

### 4.1 BaseEngine (abstrakce)

```python
class BaseEngine(ABC):
    """Abstraktní base pro všechny DB enginy."""

    @abstractmethod
    async def connect(self) -> None: ...

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
```

### 4.2 Data classes (výsledky)

```python
@dataclass
class DBInfo:
    engine: str              # "sqlite", "postgresql", "mysql", "mssql"
    version: str             # "3.45.0", "16.2", "8.0.36"
    name: str                # název DB / cesta k souboru
    size_approx: str         # "~2.5 MB", "unknown"

@dataclass
class ColumnInfo:
    name: str
    type: str                # originální typ ("VARCHAR(255)")
    type_friendly: str       # popisný typ ("text, max 255 chars")
    nullable: bool
    default: str | None
    is_primary_key: bool
    is_foreign_key: bool
    foreign_key_table: str | None
    foreign_key_column: str | None
    description: str | None  # z DB metadata pokud existuje

@dataclass
class TableInfo:
    name: str
    row_count: int
    column_count: int
    has_primary_key: bool
    foreign_keys_out: int    # počet FK z této tabulky
    foreign_keys_in: int     # počet FK do této tabulky

@dataclass
class TableDetail:
    name: str
    columns: list[ColumnInfo]
    indexes: list[IndexInfo]
    primary_key: str | None
    foreign_keys: list[ForeignKeyInfo]
    sample_data: list[dict]
    stats: TableStats

@dataclass
class IndexInfo:
    name: str
    columns: list[str]
    unique: bool

@dataclass
class ForeignKeyInfo:
    column: str
    references_table: str
    references_column: str

@dataclass
class TableStats:
    row_count: int
    avg_row_size: str        # "~1.2 KB"
    total_size: str          # "~45 MB"
    null_counts: dict[str, int]  # {column_name: null_count}
    value_distribution: dict[str, dict]  # {column: {value: count}} pro TOP 10

@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict]
    row_count: int
    truncated: bool          # true pokud bylo oříznuto
    execution_time_ms: int
    sql: str                 # provedený SQL
    warning: str | None      # varování (např. "result truncated")
```

### 4.3 URL Parsing

```python
# Formáty connection stringů:
# sqlite:///path/to/db.db          → SQLite soubor
# sqlite:///:memory:               → SQLite in-memory
# postgresql://user:pass@host:5432/dbname  → PostgreSQL
# mysql://user:pass@host:3306/dbname       → MySQL
# mssql://user:pass@host:1433/dbname       → MSSQL

def get_engine(url: str) -> BaseEngine:
    """Automaticky rozpozná engine z URL."""
```

### 4.4 SQLite Engine (built-in)

```python
class SQLiteEngine(BaseEngine):
    """SQLite engine — žádné externí závislosti."""

    # Volby:
    # - WAL mode pro současné čtení
    # - Foreign keys enforcement
    # - Full schema introspection přes pragma
    # - Row count přes sqlite_stat1 (přesný) nebo COUNT(*)

    async def get_tables(self) -> list[TableInfo]:
        # SELECT * FROM sqlite_master WHERE type='table'
        # + pragma table_info pro každou tabulku
        # + pragma index_info pro každou tabulku
        # + count(*) pro row_count

    async def get_table_detail(self, table: str) -> TableDetail:
        # pragma table_xinfo → sloupce + FK
        # pragma index_xinfo → indexy
        # SELECT * FROM table LIMIT 5 → sample data
        # pragma page_count * pragma page_size → velikost
```

### 4.5 PostgreSQL Engine (optional)

```python
class PostgresEngine(BaseEngine):
    """PostgreSQL engine — vyžaduje psycopg[binary]>=3.1.0."""

    # Lazy import: psycopg
    # Pokud nainstalovaný → import, jinak → chybová hláška

    async def get_tables(self) -> list[TableInfo]:
        # information_schema.tables + pg_stat_user_tables
        # + information_schema.columns
        # + pg_constraint pro FK

    async def get_table_detail(self, table: str) -> TableDetail:
        # information_schema.columns + pg_description pro popisky
        # pg_indexes + pg_constraint
        # pg_size_pretty(pg_total_relation_size()) pro velikost
```

### 4.6 MySQL Engine (optional)

```python
class MySQLEngine(BaseEngine):
    """MySQL engine — vyžaduje pymysql>=1.1.0."""

    async def get_tables(self) -> list[TableInfo]:
        # information_schema.tables + information_schema.columns
        # + information_schema.key_column_usage pro FK

    async def get_table_detail(self, table: str) -> TableDetail:
        # DESCRIBE table + SHOW CREATE TABLE
        # SHOW INDEX FROM table
```

### 4.7 MSSQL Engine (optional)

```python
class MSSQLEngine(BaseEngine):
    """MSSQL engine — vyžaduje pyodbc>=5.1.0 + ODBC driver."""

    async def get_tables(self) -> list[TableInfo]:
        # sys.tables + sys.columns + sys.foreign_keys
        # + sys.dm_db_partition_stats pro velikost

    async def get_table_detail(self, table: str) -> TableDetail:
        # sys.columns + sys.types + sys.indexes
        # + sys.foreign_key_columns
```

---

## 5. Nástroje — Detailní návrh

### 5.1 `test_connection`
```python
@mcp.tool()
async def test_connection() -> str:
    """
    Ověř připojení k databázi a vrať základní informace.

    Použij KDYŽ: potřebuješ zjistit typ DB, verzi, velikost,
    nebo ověřit že připojení funguje.

    Vrací: typ engine, verze, název DB, velikost, počet tabulek.
    """
```

### 5.2 `list_tables`
```python
@mcp.tool()
async def list_tables(
    include_stats: bool = True
) -> str:
    """
    Seznam všech tabulek v databázi s metadata.

    Použij KDYŽ: potřebuješ přehled co je v DB, kolik tabulek existuje,
    jaké jsou jejich vztahy. První krok při práci s neznámou DB.

    Vrací: seznam tabulek s počty řádků, sloupců, FK vztahy.
    """
```

### 5.3 `inspect_table`
```python
@mcp.tool()
async def inspect_table(
    table_name: str,
    include_sample: bool = True,
    sample_size: int = 5
) -> str:
    """
    Detailní pohled na tabulku: sloupce, typy, indexy, FK, ukázková data.

    Použij KDYŽ: potřebuješ pochopit strukturu konkrétní tabulky,
    jaké sloupce jsou, jaké typy, jaké jsou vztahy k jiným tabulkám.

    Vrací: kompletní přehled tabulky s kontextem pro LLM.
    """
```

### 5.4 `query`
```python
@mcp.tool()
async def query(
    sql: str,
    params: str = "{}"
) -> str:
    """
    Proveď bezpečný SQL dotaz a vrať výsledky.

    Použij KDYŽ: potřebuješ provést konkrétní SQL dotaz.
    Všechny dotazy jsou parametrizované a prochází safety check.

    BEZPEČNOST:
    - Read-only default: žádný INSERT/UPDATE/DELETE/DROP
    - Parametrizované dotazy: žádný string formatting
    - Max 1000 řádků, max 30s timeout

    Parametry: JSON dict pro parametrizované dotazy.
    Příklad: sql="SELECT * FROM users WHERE id = :id", params='{"id": 42}'
    """
```

### 5.5 `natural_query`
```python
@mcp.tool()
async def natural_query(
    question: str
) -> str:
    """
    Napiš otázku v přirozeném jazyku a já ji převedu na SQL, provedu a vrátím výsledky.

    Použij KDYŽ: nevíš přesný SQL, nebo chceš rychlou odpověď na otázku o datech.
    Příklady: "Kolik uživatelů má objednávky?", "Jaký produkt se nejvíce prodává?"

    Vrací: vygenerovaný SQL + výsledky + vysvětlení.
    """
```

### 5.6 `profile_database`
```python
@mcp.tool()
async def profile_database(
    table_name: str = ""
) -> str:
    """
    Kompletní profil celé DB nebo konkrétní tabulky.

    Použij KDYŽ: potřebuješ pochopit data — distribuce hodnot, NULL rates,
    velikosti, vztahy. Ideální první krok před psaním dotazů.

    Bez parametru: profil celé DB (souhrn tabulek, vztahy, velikosti).
    S parametrem: detailní profil tabulky (distribuce, null rates, TOP hodnoty).

    Vrací: statistický přehled kontextualizovaný pro LLM.
    """
```

### 5.7 `schema_graph`
```python
@mcp.tool()
async def schema_graph() -> str:
    """
    Vizualizuj vztahy mezi tabulkami jako Mermaid diagram.

    Použij KDYŽ: potřebuješ vidět jak jsou tabulky propojené,
    které mají FK vztahy, celkovou strukturu DB.

    Vrací: Mermaid diagram definici (renderuj v markdown).
    """
```

---

## 6. Safety Layer — Detailní návrh

### 6.1 SQL Validation Pipeline

```
Vstupní SQL → normalize → parse → classify → validate → execute/reject
```

### 6.2 Klasifikace dotazů

```python
class QueryType(Enum):
    SAFE_READ = "safe_read"          # SELECT, EXPLAIN, PRAGMA
    UNSAFE_READ = "unsafe_read"      # SELECT s funkcemi které mohou měnit stav
    WRITE = "write"                   # INSERT, UPDATE, DELETE
    DANGEROUS = "dangerous"           # DROP, ALTER, CREATE, TRUNCATE
    UNKNOWN = "unknown"               # nerozpoznaný

# Regex patterns pro klasifikaci:
SAFE_READ_PATTERNS = [
    r"^\s*SELECT\b",
    r"^\s*EXPLAIN\b",
    r"^\s*PRAGMA\b",
    r"^\s*SHOW\b",
    r"^\s*DESCRIBE\b",
    r"^\s*WITH\b.*SELECT",  # CTE zakončené SELECT
]

WRITE_PATTERNS = [
    r"^\s*INSERT\b",
    r"^\s*UPDATE\b",
    r"^\s*DELETE\b",
    r"^\s*REPLACE\b",
    r"^\s*MERGE\b",
]

DANGEROUS_PATTERNS = [
    r"^\s*DROP\b",
    r"^\s*ALTER\b",
    r"^\s*CREATE\b",
    r"^\s*TRUNCATE\b",
    r"^\s*GRANT\b",
    r"^\s*REVOKE\b",
]
```

### 6.3 Safety checks

```python
class SafetyConfig:
    read_only: bool = True            # default: žádný zápis
    max_result_rows: int = 1000       # max řádků
    max_query_time_seconds: int = 30  # timeout
    max_output_bytes: int = 50_000   # max výstup pro LLM
    allowed_statements: list[str]     # whitelist (pokud chceme jen SELECT)

class SafetyValidator:
    def validate(self, sql: str, config: SafetyConfig) -> SafetyResult:
        """
        1. Normalize SQL (odstranit komentáře, whitespace)
        2. Klasifikovat typ dotazu
        3. Pokud read_only=True a dotaz je WRITE/DANGEROUS → zamítnout
        4. Zkontrolovat délku výsledku
        5. Vrátit SafetyResult(approved=True/False, reason, query_type)
        """
```

### 6.4 SQL Injection Prevention

```python
# ŽÁDNÝ string formatting v SQL:
# ŠPATNĚ: f"SELECT * FROM {table}"     → SQL injection
# ŠPATNELY: "SELECT * FROM %s" % table  → SQL injection
# SPRÁVNĚ: cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))

# Pro nástroj `query`:
# - Povinné parametrizované dotazy
# - Parametry musí být JSON dict
# - Engine použije svůj paramstyle (?, %s, :name)

# Pro `natural_query`:
# - LLM vygeneruje SQL → safety check → execution
# - Pokud safety check selhal → vrátí chybu s vysvětlením
```

---

## 7. Schema Inspector — Detailní návrh

### 7.1 Zdroje dat (per engine)

| Metadata | SQLite | PostgreSQL | MySQL | MSSQL |
|----------|--------|------------|-------|-------|
| Tabulky | sqlite_master | information_schema.tables | information_schema.tables | sys.tables |
| Sloupce | pragma table_info | information_schema.columns | information_schema.columns | sys.columns |
| Typy | (z table_info) | pg_type + pg_catalog | data_type z columns | sys.types |
| Indexy | pragma index_info | pg_indexes | SHOW INDEX | sys.indexes |
| FK | pragma foreign_key_list | pg_constraint | key_column_usage | sys.foreign_keys |
| Velikost | pragma page_count | pg_total_relation_size | data_length | sys.dm_db_partition_stats |
| Popisky | (není) | pg_description | (není) | sys.extended_properties |
| Statistiky | (není) | pg_stat_user_tables | (není) | sys.dm_db_index_usage_stats |

### 7.2 Relationship Discovery

```python
class RelationshipDiscovery:
    """Automaticky objeví vztahy mezi tabulkami."""

    def discover_foreign_keys(self, tables: list[TableDetail]) -> list[Relationship]:
        """
        1. Přečte explicitní FK z constraintů
        2. Hledá implicitní FK podle naming conventions:
           - {table}_id → table.id
           - {table}_ids (array) → table.id
        3. Detekuje junction tables (2+ FK = many-to-many)
        4. Vrací list[Relationship] s cardinalitou
        """

@dataclass
class Relationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str  # "one-to-one", "one-to-many", "many-to-many"
    is_explicit: bool  # z DB constraint nebo z naming convention
```

### 7.3 Schema Graph

```python
def generate_mermaid(tables: list[TableDetail], relationships: list[Relationship]) -> str:
    """
    Generuje Mermaid diagram:

    ```mermaid
    erDiagram
        users {
            int id PK
            string name
            string email
        }
        orders {
            int id PK
            int user_id FK
            datetime created_at
        }
        users ||--o{ orders : "has"
    ```
    """
```

---

## 8. LLM Formatter — Detailní návrh

### 8.1 Typ překladů

```python
TYPE_TRANSLATIONS = {
    # SQLite
    "INTEGER": "integer",
    "REAL": "decimal number",
    "TEXT": "text",
    "BLOB": "binary data",
    "VARCHAR": "text",
    "BOOLEAN": "true/false",
    "DATETIME": "date and time",
    "DATE": "date only",
    "TIMESTAMP": "date and time",

    # PostgreSQL
    "integer": "integer",
    "bigint": "large integer",
    "smallint": "small integer",
    "numeric": "precise decimal",
    "real": "decimal number",
    "double precision": "decimal number",
    "character varying": "text",
    "text": "text",
    "boolean": "true/false",
    "timestamp with time zone": "date and time (timezone)",
    "timestamp without time zone": "date and time",
    "json": "JSON data",
    "jsonb": "JSON data (optimized)",
    "uuid": "unique identifier",
    "array": "list of values",
}
```

### 8.2 Formátování výstupu

```python
class LLMFormatter:
    def format_query_result(self, result: QueryResult) -> str:
        """
        Formátuje výsledek dotazu pro LLM:

        ## Query Results
        **SQL:** SELECT u.name, COUNT(o.id) as order_count FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.name
        **Rows:** 15 (of 15 total)
        **Time:** 23ms

        | Name | Order Count |
        |------|-------------|
        | Jan Novák | 12 |
        | Petr Svoboda | 8 |
        | (empty) | 3 |

        **Notes:** 3 users have no orders.
        """

    def format_table_detail(self, detail: TableDetail) -> str:
        """
        Formátuje detail tabulky:

        ## Table: users (2,456 rows, ~1.2 MB)

        ### Columns
        | # | Name | Type | Nullable | Key | Description |
        |---|------|------|----------|-----|-------------|
        | 1 | id | integer | no | PK | Auto-increment ID |
        | 2 | name | text (max 100 chars) | no | | Full name |
        | 3 | email | text (max 255 chars) | no | UNIQUE | Email address |
        | 4 | created_at | date and time | yes | | Registration date |

        ### Relationships
        - `users.id` → `orders.user_id` (one-to-many, 12 orders per user avg)
        - `users.id` → `reviews.user_id` (one-to-many)

        ### Indexes
        - `idx_users_email` ON (email) UNIQUE
        - `idx_users_created` ON (created_at)

        ### Sample Data
        | id | name | email | created_at |
        |----|------|-------|------------|
        | 1 | Jan Novák | jan@example.com | 2024-01-15T10:30:00 |
        | 2 | Petr Svoboda | petr@example.com | 2024-02-20T14:45:00 |
        """

    def format_profile(self, profile: DatabaseProfile) -> str:
        """
        Formátuje profil DB:

        ## Database Profile
        **Engine:** PostgreSQL 16.2
        **Size:** ~45 MB
        **Tables:** 12

        ### Overview
        | Table | Rows | Columns | FK In | FK Out | Size |
        |-------|------|---------|-------|--------|------|
        | users | 2,456 | 8 | 3 | 2 | ~1.2 MB |
        | orders | 15,892 | 6 | 1 | 1 | ~8.5 MB |

        ### Relationships (5 explicit, 2 inferred)
        - users → orders (one-to-many)
        - users → reviews (one-to-many)
        - orders → order_items (one-to-many)
        - products → order_items (one-to-many)
        - categories → products (one-to-many)

        ### Health
        - 3 tables with no indexes beyond PK
        - 2 tables with high NULL rates (>50%)
        - 1 circular reference detected (users → orders → users)
        """
```

### 8.3 Truncation strategy

```python
def truncate_for_llm(text: str, max_bytes: int = 50_000) -> tuple[str, bool]:
    """
    1. Pokud text < max_bytes → vrátit celý
    2. Pokud text > max_bytes:
       a. Zkrátit tabulku na prvních N řádků
       b. Přidat "... (truncated, showing 100 of 5000 rows)"
       c. Přidat summary na konec
    3. Vždycky vrátit varování
    """
```

---

## 9. Natural Language → SQL

### 9.1 Přístup
Pro `natural_query` nepoužíváme externí LLM API (to by bylo zbytečné). Místo toho:

**Strategy A — Schema-driven prompt (pro v1):**
- Načteme schéma DB
- Sestavíme kontextový prompt s tabulkami, sloupci, FK
- Využijeme jednoduché pattern matching pro běžné dotazy
- Komplexní dotazy → pošleme uživateli SQL návrh s vysvětlením

**Strategy B — LLM integration (pro v2):**
- Volitelné: pokud je nastaven `OPENAI_API_KEY` nebo `ANTHROPIC_API_KEY`
- Pošleme schema + otázku na LLM
- Dostaneme SQL zpět → validace → execution

### 9.2 Pattern matching pro běžné dotazy

```python
PATTERNS = {
    # "kolik [table]" → COUNT(*)
    r"kolik\s+(\w+)": "SELECT COUNT(*) as count FROM {table}",

    # "všechny/zobraz [table]" → SELECT * LIMIT 100
    r"(?:všechny|zobraz|ukaž)\s+(\w+)": "SELECT * FROM {table} LIMIT 100",

    # "[table] s [column] [value]" → SELECT WHERE
    r"(\w+)\s+s\s+(\w+)\s+[=:]\s*(\S+)": "SELECT * FROM {table} WHERE {column} = {value}",

    # "největší/nejmenší/nejlepší [column] v [table]" → ORDER BY
    r"nej(?:větší|menší|lepší|dražší|levnější)\s+(\w+)\s+v\s+(\w+)":
        "SELECT * FROM {table} ORDER BY {column} DESC LIMIT 10",
}
```

### 9.3 Fallback
Pokud pattern nesedí → vrátíme:
```sql
-- Nepodařilo se automaticky přeložit otázku na SQL.
-- Zkuste: query("SELECT ...")
-- Nebo napište přesnější dotaz.
```

---

## 10. Konfigurace

### 10.1 Environment Variables

```env
# === POVINNÉ ===
DATABASE_URL=sqlite:///data/test.db

# === BEZPEČNOST ===
DATABASE_READ_ONLY=true          # Read-only režim (default: true)
DATABASE_WRITE_ENABLED=false     # Povolit zápis (default: false)
DATABASE_MAX_ROWS=1000           # Max řádků na dotaz (default: 1000)
DATABASE_MAX_QUERY_TIME=30       # Max sekundy na dotaz (default: 30)
DATABASE_MAX_OUTPUT_BYTES=50000  # Max výstup bytes (default: 50000)

# === VOLITELNÉ ===
DATABASE_SAMPLE_SIZE=5           # Počet sample řádků (default: 5)
DATABASE_PROFILE_TOP_N=10        # TOP N hodnot v profilu (default: 10)

# === LLM (pro natural_query v2) ===
OPENAI_API_KEY=                  # Volitelné: OpenAI pro SQL generation
ANTHROPIC_API_KEY=               # Volitelné: Anthropic pro SQL generation
```

### 10.2 Config class

```python
@dataclass
class DatabaseConfig:
    url: str
    read_only: bool = True
    write_enabled: bool = False
    max_rows: int = 1000
    max_query_time: int = 30
    max_output_bytes: int = 50_000
    sample_size: int = 5
    profile_top_n: int = 10
    openai_key: str | None = None
    anthropic_key: str | None = None

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL environment variable is required")
        return cls(
            url=url,
            read_only=os.environ.get("DATABASE_READ_ONLY", "true").lower() == "true",
            # ... etc
        )
```

---

## 11. Server — Tool Registration

```python
async def create_server(config: DatabaseConfig) -> MCPServer:
    server = MCPServer(
        name="mcp-database-server",
        version="0.1.0",
    )

    engine = get_engine(config.url)
    await engine.connect()

    safety = SafetyValidator(config)
    inspector = SchemaInspector(engine)
    formatter = LLMFormatter(config)

    @server.tool()
    async def test_connection() -> str:
        info = await engine.get_db_info()
        return formatter.format_db_info(info)

    @server.tool()
    async def list_tables(include_stats: bool = True) -> str:
        tables = await engine.get_tables()
        return formatter.format_table_list(tables)

    @server.tool()
    async def inspect_table(table_name: str, include_sample: bool = True, sample_size: int = 5) -> str:
        detail = await engine.get_table_detail(table_name)
        return formatter.format_table_detail(detail)

    @server.tool()
    async def query(sql: str, params: str = "{}") -> str:
        validation = safety.validate(sql)
        if not validation.approved:
            return f"BLOCKED: {validation.reason}"
        result = await engine.execute_query(sql, json.loads(params))
        return formatter.format_query_result(result)

    @server.tool()
    async def natural_query(question: str) -> str:
        # Pattern matching → SQL → validate → execute → format
        ...

    @server.tool()
    async def profile_database(table_name: str = "") -> str:
        ...

    @server.tool()
    async def schema_graph() -> str:
        ...

    return server
```

---

## 12. Testy — Plán

### 12.1 Unit tests (per modul)

| Modul | Testy | Popis |
|-------|-------|-------|
| engines/sqlite.py | 12 | connect, tables, columns, FK, query, sample, stats |
| safety.py | 10 | read-only block, write detection, injection, limits |
| schema_inspector.py | 8 | FK discovery, naming conventions, junction tables |
| formatters/llm.py | 10 | formatování, truncation, null handling |
| config.py | 5 | env parsing, validation, defaults |

### 12.2 Integration tests

| Test | Popis |
|------|-------|
| Full workflow | connect → list → inspect → query → format |
| Safety integration | pokus o SQL injection → zamítnuto |
| Multi-table query | JOIN query → formátovaný výstup |
| Large result truncation | 5000 řádků → oříznuto na 1000 |
| Profile workflow | profile_database → schema_graph |

### 12.3 STDIO tests

| Test | Popis |
|------|-------|
| Docker build | Dockerfile se sestaví |
| STDIO handshake | initialize → initialized |
| Tool listing | tools/list vrací 7 nástrojů |
| Tool call | tools/call test_connection |

**Target: 55+ testů**

---

## 13. Bezpečnostní kontrolní seznam

- [ ] Žádné SQL injection přes string formatting
- [ ] Read-only default — všechny write operace zamítnuty
- [ ] Parametrizované dotazy povinné pro `query` tool
- [ ] Query timeout 30s
- [ ] Row limit 1000
- [ ] Output truncation 50KB
- [ ] Žádné heslo/credential v log outputu
- [ ] Docker: non-root user
- [ ] Environment variables pro secrets (nikdy v kódu)

---

## 14. Publikační checklist

- [ ] GitHub repo: `mcp-database-server`
- [ ] PyPI: `mcp-database-server`
- [ ] HF: `Lukynnnn/mcp-database-server`
- [ ] CI: Python 3.10-3.13 + Docker build
- [ ] Publish workflow: PyPI OIDC
- [ ] README: badges, install, examples
- [ ] .env.example
- [ ] LICENSE: MIT

---

## 15. Rozhodnutí a kompromisy

| Otázka | Rozhodnutí | Důvod |
|--------|------------|-------|
| natural_query s LLM? | Pattern matching v1, LLM v2 | Bez nutnosti API klíče |
| Kolik engineů? | 4 (SQLite + 3 optional) | Pokrytí 95% trhu |
| Async? | Ano | MCP SDK je async |
| pip install? | Ano, s extras | `pip install mcp-database-server[postgres]` |
| Typování? | dataclasses, ne Pydantic | Méně závislostí |
| Server framework? | MCPSector z MCP SDK | Stejně jako MCP Manager |

---

Poslední aktualizace: 2026-08-26
