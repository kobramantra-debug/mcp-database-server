"""LLM-friendly output formatting for database results."""

from dataclasses import dataclass
from src.config import DatabaseConfig
from src.engines.base import DBInfo, TableInfo, TableDetail, TableStats, QueryResult


TYPE_TRANSLATIONS = {
    "INTEGER": "integer",
    "INT": "integer",
    "BIGINT": "large integer",
    "SMALLINT": "small integer",
    "TINYINT": "tiny integer",
    "REAL": "decimal number",
    "FLOAT": "decimal number",
    "DOUBLE": "decimal number",
    "DOUBLE PRECISION": "decimal number",
    "NUMERIC": "precise decimal",
    "DECIMAL": "precise decimal",
    "TEXT": "text",
    "VARCHAR": "text",
    "CHAR": "text",
    "BOOLEAN": "true/false",
    "BOOL": "true/false",
    "DATETIME": "date and time",
    "DATE": "date only",
    "TIMESTAMP": "date and time",
    "TIMESTAMP WITH TIME ZONE": "date and time (timezone)",
    "TIMESTAMP WITHOUT TIME ZONE": "date and time",
    "BLOB": "binary data",
    "BYTEA": "binary data",
    "JSON": "JSON data",
    "JSONB": "JSON data (optimized)",
    "UUID": "unique identifier",
    "ARRAY": "list of values",
    "SERIAL": "auto-increment integer",
    "BIGSERIAL": "auto-increment large integer",
}


class LLMFormatter:
    def __init__(self, config: DatabaseConfig):
        self.config = config

    def translate_type(self, raw_type: str) -> str:
        upper = raw_type.upper().strip()
        if "(" in upper:
            base = upper.split("(")[0].strip()
            size = upper.split("(")[1].rstrip(")")
            translated = TYPE_TRANSLATIONS.get(base, base.lower())
            return f"{translated} (max {size} chars)" if "text" in translated else translated
        return TYPE_TRANSLATIONS.get(upper, raw_type.lower())

    def format_number(self, n) -> str:
        if n is None:
            return "(empty)"
        if isinstance(n, float):
            return f"{n:,.2f}"
        if isinstance(n, int):
            return f"{n:,}"
        return str(n)

    def format_value(self, v) -> str:
        if v is None:
            return "(empty)"
        if isinstance(v, float):
            return f"{v:,.2f}"
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)

    def truncate_for_llm(self, text: str) -> tuple[str, bool]:
        max_bytes = self.config.max_output_bytes
        if len(text.encode("utf-8")) <= max_bytes:
            return text, False
        lines = text.split("\n")
        truncated_lines = []
        byte_count = 0
        for line in lines:
            line_bytes = len(line.encode("utf-8")) + 1
            if byte_count + line_bytes > max_bytes - 200:
                truncated_lines.append("... (output truncated)")
                break
            truncated_lines.append(line)
            byte_count += line_bytes
        return "\n".join(truncated_lines), True

    def format_db_info(self, info: DBInfo) -> str:
        lines = [
            f"## Database Connection OK",
            f"- **Engine:** {info.engine}",
            f"- **Version:** {info.version}",
            f"- **Name:** {info.name}",
            f"- **Size:** {info.size_approx}",
        ]
        text = "\n".join(lines)
        text, _ = self.truncate_for_llm(text)
        return text

    def format_table_list(self, tables: list[TableInfo]) -> str:
        if not tables:
            return "## Tables\nNo tables found in this database."

        lines = [
            f"## Tables ({len(tables)} total)",
            "",
            "| Table | Rows | Columns | FK In | FK Out |",
            "|-------|------|---------|-------|--------|",
        ]

        for t in tables:
            lines.append(
                f"| {t.name} | {self.format_number(t.row_count)} | "
                f"{t.column_count} | {t.foreign_keys_in} | {t.foreign_keys_out} |"
            )

        text = "\n".join(lines)
        text, _ = self.truncate_for_llm(text)
        return text

    def format_table_detail(self, detail: TableDetail) -> str:
        lines = [
            f"## Table: {detail.name}",
            "",
            "### Columns",
            "| # | Name | Type | Nullable | Key |",
            "|---|------|------|----------|-----|",
        ]

        for i, col in enumerate(detail.columns, 1):
            key = ""
            if col.is_primary_key:
                key = "PK"
            elif col.is_foreign_key:
                key = f"FK -> {col.foreign_key_table}.{col.foreign_key_column}"
            lines.append(
                f"| {i} | {col.name} | {self.translate_type(col.type)} | "
                f"{'yes' if col.nullable else 'no'} | {key} |"
            )

        if detail.foreign_keys:
            lines.extend(["", "### Relationships"])
            for fk in detail.foreign_keys:
                lines.append(
                    f"- `{detail.name}.{fk.column}` -> "
                    f"`{fk.references_table}.{fk.references_column}`"
                )

        if detail.indexes:
            lines.extend(["", "### Indexes"])
            for idx in detail.indexes:
                unique = " UNIQUE" if idx.unique else ""
                lines.append(f"- `{idx.name}` ON ({', '.join(idx.columns)}){unique}")

        if detail.sample_data:
            lines.extend(["", "### Sample Data (first 5 rows)"])
            if detail.sample_data:
                headers = list(detail.sample_data[0].keys())
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for row in detail.sample_data:
                    vals = [self.format_value(row.get(h)) for h in headers]
                    lines.append("| " + " | ".join(vals) + " |")

        if detail.stats:
            lines.extend(["", "### Statistics"])
            lines.append(f"- **Row count:** {self.format_number(detail.stats.row_count)}")
            lines.append(f"- **Avg row size:** {detail.stats.avg_row_size}")
            lines.append(f"- **Total size:** {detail.stats.total_size}")

            if detail.stats.null_counts:
                non_zero = {k: v for k, v in detail.stats.null_counts.items() if v > 0}
                if non_zero:
                    lines.append("- **NULL counts:**")
                    for col, count in non_zero.items():
                        lines.append(f"  - {col}: {self.format_number(count)}")

        text = "\n".join(lines)
        text, _ = self.truncate_for_llm(text)
        return text

    def format_query_result(self, result: QueryResult) -> str:
        lines = [
            "## Query Results",
            f"**SQL:** `{result.sql}`",
            f"**Rows:** {result.row_count}{' (truncated)' if result.truncated else ''}",
            f"**Time:** {result.execution_time_ms}ms",
        ]

        if result.warning:
            lines.append(f"**Warning:** {result.warning}")

        if result.columns and result.rows:
            lines.append("")
            lines.append("| " + " | ".join(result.columns) + " |")
            lines.append("| " + " | ".join(["---"] * len(result.columns)) + " |")
            for row in result.rows:
                vals = [self.format_value(row.get(c)) for c in result.columns]
                lines.append("| " + " | ".join(vals) + " |")
        elif not result.rows:
            lines.append("\n*No rows returned.*")

        text = "\n".join(lines)
        text, _ = self.truncate_for_llm(text)
        return text

    def format_profile(self, profile_data: dict) -> str:
        lines = ["## Database Profile", ""]

        if "db_info" in profile_data:
            info = profile_data["db_info"]
            lines.extend([
                f"**Engine:** {info.engine} {info.version}",
                f"**Size:** {info.size_approx}",
                f"**Tables:** {profile_data.get('table_count', 'unknown')}",
            ])

        if "tables" in profile_data:
            lines.extend(["", "### Overview", "| Table | Rows | Columns | FK In | FK Out |", "|-------|------|---------|-------|--------|"])
            for t in profile_data["tables"]:
                lines.append(
                    f"| {t.name} | {self.format_number(t.row_count)} | "
                    f"{t.column_count} | {t.foreign_keys_in} | {t.foreign_keys_out} |"
                )

        if "relationships" in profile_data and profile_data["relationships"]:
            lines.extend(["", f"### Relationships ({len(profile_data['relationships'])})"])
            for rel in profile_data["relationships"]:
                explicit = "explicit" if rel.is_explicit else "inferred"
                lines.append(f"- {rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column} ({rel.cardinality}, {explicit})")

        if "junction_tables" in profile_data and profile_data["junction_tables"]:
            lines.extend(["", "### Junction Tables (many-to-many)"])
            for jt in profile_data["junction_tables"]:
                lines.append(f"- `{jt}`")

        if "table_stats" in profile_data:
            lines.extend(["", "### Table Statistics"])
            for table_name, stats in profile_data["table_stats"].items():
                lines.append(f"\n#### {table_name}")
                lines.append(f"- Rows: {self.format_number(stats.row_count)}")
                lines.append(f"- Size: {stats.total_size}")
                if stats.null_counts:
                    non_zero = {k: v for k, v in stats.null_counts.items() if v > 0}
                    if non_zero:
                        lines.append("- NULL columns:")
                        for col, count in non_zero.items():
                            lines.append(f"  - {col}: {self.format_number(count)}")

        text = "\n".join(lines)
        text, _ = self.truncate_for_llm(text)
        return text

    def format_schema_graph(self, mermaid: str) -> str:
        lines = [
            "## Schema Graph",
            "",
            "```mermaid",
            mermaid,
            "```",
        ]
        return "\n".join(lines)
