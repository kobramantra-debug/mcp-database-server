# MCP Database Server - Vývojový průvodce

## 1. Název a identita
- **Název:** MCP Database Server
- **PyPI:** `mcp-database-server`
- **GitHub:** `https://github.com/kobramantra-debug/mcp-database-server`
- **HF:** `https://huggingface.co/Lukynnnn/mcp-database-server`
- **Cílový Python:** 3.10+
- **SDK:** mcp[cli]>=2.0.0 (MCPServer z mcp.server.mcpserver)

## 2. Proč existuje
Oficiální `server-postgres` a `server-sqlite` byly **archivovány kvůli SQL injection CVE**. Existující alternativy (@bytebase/dbhub) jsou read-only a omezené. Žádný DB MCP server nenabízí:
- Multi-DB podporu z jednoho serveru
- Bezpečné parametrizované dotazy s read-only defaultem
- LLM-friendly výstup (kontextualizovaná data, ne raw tabulky)
- Automatickou schema introspeci a relationship discovery

## 3. Designové principy
1. **Reasoning interface, ne execution wrapper** — nástroje navržené pro myšlení agenta
2. **Bezpečnost na prvním místě** — read-only default, žádné SQL injection
3. **LLM-friendly output** — data kontextualizovaná pro model, ne pro člověka
4. **Multi-engine** — SQLite (built-in), PostgreSQL, MySQL, MSSQL (optional deps)
5. **Méně nástrojů = lepší výsledky** — max 8 nástrojů, žádný nepotřebný

## 4. Architektura

```
src/
  __init__.py          # Package init
  __main__.py          # Entry point (python -m mcp_database_universal)
  server.py            # MCPServer with all tools
  engines/
    __init__.py
    base.py            # Abstract DBEngine
    sqlite.py          # SQLite engine (built-in)
    postgres.py        # PostgreSQL engine (optional)
    mysql.py           # MySQL engine (optional)
    mssql.py           # MSSQL engine (optional)
  formatters/
    __init__.py
    llm_formatter.py   # LLM-friendly output formatting
  safety.py            # Query validation, read-only enforcement
  schema_inspector.py  # Schema introspection + relationships
```

## 5. Nástroje (max 8)

### list_tables
- Seznam všech tabulek s metadata (řádky, typy, popisy)
- Vstup: (žádný)
- Výstup: strukturovaný seznam tabulek

### inspect_table
- Detailní pohled na tabulku: sloupce, typy, indexy, FK, sample data, statistiky
- Vstup: table_name, include_sample (bool, default true)
- Výstup: kompletní přehled tabulky

### query
- Bezpečný SQL dotaz (parametrizovaný, read-only check)
- Vstup: sql, params (optional dict)
- Výstup: LLM-formátované výsledky + metainfo

### natural_query
- Přirozený jazyk → SQL → provedení → výsledky
- Vstup: question (string)
- Výstup: SQL + výsledky + explanation

### profile_database
- Kompletní profil: počty řádků, velikosti, distribuce hodnot, NULL rates
- Vstup: (žádný nebo table_name)
- Výstup: statistický přehled

### schema_graph
- Vizuální graf vztahů mezi tabulkami (Mermaid formát)
- Vstup: (žádný)
- Výstup: Mermaid diagram definice

### test_connection
- Ověření připojení + základní info o DB (typ, verze, velikost)
- Vstup: (žádný)
- Výstup: info o připojení

## 6. Safety Layer
- **Read-only default:** všechny dotazy prochází přes validation
- **Write detection:** detekce INSERT/UPDATE/DELETE/DROP → zamítnuto pokud write_enabled=false
- **Query limits:** max_result_rows=1000, max_query_time=30s
- **SQL injection prevention:** parametrizované dotazy, žádný string formatting
- **Truncation:** výstup omezen na 50KB pro LLM kontext

## 7. Engines

### SQLite (built-in)
- Python standard library: `sqlite3`
- Žádné externí závislosti
- Podpora: :memory:, soubor, WAL mode

### PostgreSQL (optional)
- Dep: `psycopg[binary]>=3.1.0`
- Full schema introspection, pg_stat, array types

### MySQL (optional)
- Dep: `pymysql>=1.1.0`
- Standard MySQL introspection

### MSSQL (optional)
- Dep: `pyodbc>=5.1.0`
- Azure SQL + on-premise

## 8. LLM-Friendly Output
- Sloupce přejmenované na čitelné názvy
- Čísla formátovaná (1,234,567)
- Datumy v ISO formatu
- NULL hodnoty zobrazené jako "(empty)"
- Výsledky doplněné o kontext (celkový počet, čas dotazu)
- Automatický překlad technických typů na popisné (VARCHAR(255) → "text (max 255 chars)")

## 9. Kroky implementace
1. [ ] Vytvořit projektovou strukturu
2. [ ] Implementovat base engine + SQLite engine
3. [ ] Implementovat safety layer
4. [ ] Implementovat schema inspector
5. [ ] Implementovat LLM formatter
6. [ ] Implementovat MCPServer s nástroji
7. [ ] Napsat testy (50+)
8. [ ] Docker build + STDIO test
9. [ ] PostgreSQL engine (optional)
10. [ ] MySQL engine (optional)
11. [ ] Publikovat

## 10. Testing strategy
- **Unit tests:** každý engine zvlášť s in-memory SQLite
- **Integration tests:** PostgreSQL (pokud dostupný)
- **STDIO tests:** Docker handshake test
- **Safety tests:** SQL injection attempts, write detection
- **Formatter tests:** LLM output format validation

## 11. Konfigurace
```env
# Povinné
DATABASE_URL=sqlite:///path/to/db.db

# Volitelné
DATABASE_WRITE_ENABLED=false     # Povolit zápis
DATABASE_MAX_ROWS=1000           # Max řádků na dotaz
DATABASE_MAX_QUERY_TIME=30       # Max sekundy na dotaz
DATABASE_READ_ONLY=true          # Read-only režim
```

## 12. Životní dokument
Tento soubor se průběžně aktualizuje. Poslední aktualizace: 2026-08-26.
