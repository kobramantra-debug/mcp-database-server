"""MCP Database Server — main server with 7 reasoning tools."""

import json
import re
import sys
import logging
from mcp.server.mcpserver import MCPServer
from src.config import DatabaseConfig
from src.engines.base import BaseEngine
from src.safety import SafetyValidator
from src.schema_inspector import SchemaInspector
from src.formatters.llm import LLMFormatter

logger = logging.getLogger("mcp-db")


async def create_server(config: DatabaseConfig, engine: BaseEngine) -> MCPServer:
    server = MCPServer(
        name="mcp-database-server",
        version="0.1.0",
    )

    safety = SafetyValidator(
        read_only=config.is_effectively_read_only(),
        max_rows=config.max_rows,
        max_query_time=config.max_query_time,
    )
    inspector = SchemaInspector(engine)
    formatter = LLMFormatter(config)

    @server.tool()
    async def test_connection() -> str:
        """
        Test database connection and return basic info.

        Use when: you need to verify the connection works,
        or find out the DB type, version, and size.
        Returns: engine type, version, database name, size.
        """
        try:
            info = await engine.get_db_info()
            tables = await engine.get_tables()
            result = formatter.format_db_info(info)
            result += f"\n- **Tables:** {len(tables)}"
            result += f"\n- **Read-only:** {'yes' if engine.is_read_only() else 'no'}"
            return result
        except Exception as e:
            return f"Connection failed: {str(e)}"

    @server.tool()
    async def list_tables(include_stats: bool = True) -> str:
        """
        List all tables in the database with metadata.

        Use when: you need an overview of what's in the database,
        how many tables exist, and their relationships.
        This is the first step when working with an unknown database.
        Returns: list of tables with row counts, column counts, FK relationships.
        """
        try:
            tables = await engine.get_tables()
            return formatter.format_table_list(tables)
        except Exception as e:
            return f"Error listing tables: {str(e)}"

    @server.tool()
    async def inspect_table(table_name: str, include_sample: bool = True, sample_size: int = 5) -> str:
        """
        Inspect a table's structure: columns, types, indexes, foreign keys, sample data.

        Use when: you need to understand a specific table's structure,
        what columns exist, their types, and relationships to other tables.
        Returns: complete table overview with context for LLM.
        """
        try:
            detail = await engine.get_table_detail(table_name)
            if not include_sample:
                detail.sample_data = []
            return formatter.format_table_detail(detail)
        except Exception as e:
            return f"Error inspecting table '{table_name}': {str(e)}"

    @server.tool()
    async def query(sql: str, params: str = "{}") -> str:
        """
        Execute a safe SQL query and return formatted results.

        Use when: you need to run a specific SQL query.
        All queries are parametrized and pass through safety checks.

        SAFETY:
        - Read-only by default: no INSERT/UPDATE/DELETE/DROP allowed
        - Parametrized queries: no string formatting
        - Max 1000 rows, 30s timeout

        Params: JSON dict for parameterized queries.
        Example: sql="SELECT * FROM users WHERE id = :id", params='{"id": 42}'
        """
        validation = safety.validate(sql)
        if not validation.approved:
            return f"BLOCKED: {validation.reason}"

        try:
            params_dict = json.loads(params) if params and params != "{}" else None
        except json.JSONDecodeError:
            return "BLOCKED: Invalid JSON in params"

        safe_sql = safety.ensure_limit(sql)
        result = await engine.execute_query(safe_sql, params_dict)
        return formatter.format_query_result(result)

    @server.tool()
    async def natural_query(question: str) -> str:
        """
        Ask a question in natural language and get SQL + results.

        Use when: you don't know the exact SQL, or want a quick answer
        about the data. Examples: "How many users have orders?",
        "What product sells the best?"

        Returns: generated SQL + results + explanation.
        """
        question_lower = question.lower().strip()
        tables = await engine.get_tables()
        table_names = [t.name for t in tables]
        table_map = {t.name.lower(): t.name for t in tables}

        sql = None

        count_match = re.search(r'(?:kolik|count|how many)\s+(\w+)', question_lower)
        if count_match:
            candidate = count_match.group(1)
            if candidate in table_map:
                real_name = table_map[candidate]
                sql = f'SELECT COUNT(*) as count FROM "{real_name}"'

        if not sql:
            select_match = re.search(r'(?:vsechny|zobraz|ukaž|show|select|get)\s+(\w+)', question_lower)
            if select_match:
                candidate = select_match.group(1)
                if candidate in table_map:
                    real_name = table_map[candidate]
                    sql = f'SELECT * FROM "{real_name}" LIMIT 100'

        if not sql:
            where_match = re.search(r'(\w+)\s+(?:s|where|with)\s+(\w+)\s*[=:]\s*["\']?(\w+)["\']?', question_lower)
            if where_match:
                table_cand, col_cand, val = where_match.groups()
                if table_cand in table_map:
                    real_name = table_map[table_cand]
                    sql = f'SELECT * FROM "{real_name}" WHERE "{col_cand}" = ? LIMIT 100'

        if not sql:
            top_match = re.search(r'nej(?:vetsi|mensi|lepsi|drazsi|levnejsi|best|worst|top)\s+(\w+)\s+v\s+(\w+)', question_lower)
            if not top_match:
                top_match = re.search(r'(?:top|best|worst|highest|lowest)\s+(\w+)\s+(?:in|from)\s+(\w+)', question_lower)
            if top_match:
                col_cand, table_cand = top_match.groups()
                if table_cand in table_map:
                    real_name = table_map[table_cand]
                    sql = f'SELECT * FROM "{real_name}" ORDER BY "{col_cand}" DESC LIMIT 10'

        if not sql:
            return (
                "Could not automatically translate your question to SQL.\n\n"
                "Try using the `query` tool directly with SQL, or rephrase your question.\n"
                f"Available tables: {', '.join(table_names)}\n\n"
                "Examples:\n"
                "- 'How many users are there?'\n"
                "- 'Show me all orders'\n"
                "- 'What products cost more than 100?'"
            )

        validation = safety.validate(sql)
        if not validation.approved:
            return f"Generated query was blocked: {validation.reason}"

        result = await engine.execute_query(sql)
        output = formatter.format_query_result(result)
        output = f"**Question:** {question}\n\n{output}"
        return output

    @server.tool()
    async def profile_database(table_name: str = "") -> str:
        """
        Get a complete profile of the database or a specific table.

        Use when: you need to understand the data — value distributions,
        NULL rates, sizes, relationships. Ideal first step before writing queries.

        Without parameter: database overview (table summary, relationships, sizes).
        With parameter: detailed table profile (distributions, null rates, top values).
        """
        try:
            db_info = await engine.get_db_info()
            tables = await engine.get_tables()
            relationships = await inspector.discover_relationships()
            junction_tables = inspector.detect_junction_tables(relationships)

            profile_data = {
                "db_info": db_info,
                "table_count": len(tables),
                "tables": tables,
                "relationships": relationships,
                "junction_tables": junction_tables,
            }

            if table_name:
                table_stats = {}
                try:
                    stats = await engine.get_table_stats(table_name)
                    table_stats[table_name] = stats
                except Exception:
                    pass
                profile_data["table_stats"] = table_stats

            return formatter.format_profile(profile_data)
        except Exception as e:
            return f"Error profiling database: {str(e)}"

    @server.tool()
    async def schema_graph() -> str:
        """
        Visualize table relationships as a Mermaid ER diagram.

        Use when: you need to see how tables are connected,
        which have foreign key relationships, and the overall DB structure.
        Returns: Mermaid diagram definition (render in markdown).
        """
        try:
            relationships = await inspector.discover_relationships()
            mermaid = inspector.generate_mermaid(relationships)
            return formatter.format_schema_graph(mermaid)
        except Exception as e:
            return f"Error generating schema graph: {str(e)}"

    return server
