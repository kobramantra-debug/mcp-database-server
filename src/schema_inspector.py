"""Schema inspector — discovers tables, columns, relationships."""

from dataclasses import dataclass, field
from src.engines.base import BaseEngine


@dataclass
class Relationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str  # "one-to-one", "one-to-many", "many-to-many"
    is_explicit: bool  # from DB constraint or from naming convention


class SchemaInspector:
    def __init__(self, engine: BaseEngine):
        self.engine = engine

    async def discover_relationships(self) -> list[Relationship]:
        tables = await self.engine.get_tables()
        relationships: list[Relationship] = []
        explicit_pairs: set[tuple[str, str, str, str]] = set()

        for table_info in tables:
            detail = await self.engine.get_table_detail(table_info.name)
            for fk in detail.foreign_keys:
                relationships.append(Relationship(
                    from_table=table_info.name,
                    from_column=fk.column,
                    to_table=fk.references_table,
                    to_column=fk.references_column,
                    cardinality="many-to-one",
                    is_explicit=True,
                ))
                explicit_pairs.add((
                    table_info.name, fk.column,
                    fk.references_table, fk.references_column,
                ))

        inferred = self._infer_by_naming(tables, explicit_pairs)
        relationships.extend(inferred)

        return relationships

    def _infer_by_naming(
        self,
        tables: list,
        explicit_pairs: set[tuple[str, str, str, str]],
    ) -> list[Relationship]:
        table_names = {t.name.lower() for t in tables}
        inferred: list[Relationship] = []

        for table_info in tables:
            detail = None
            for col in (table_info.columns if hasattr(table_info, 'columns') else []):
                col_lower = col.name.lower()
                if col_lower.endswith("_id") and col_lower != "id":
                    candidate_table = col_lower[:-3]
                    if candidate_table in table_names:
                        pair = (table_info.name, col.name, candidate_table, "id")
                        if pair not in explicit_pairs:
                            inferred.append(Relationship(
                                from_table=table_info.name,
                                from_column=col.name,
                                to_table=candidate_table,
                                to_column="id",
                                cardinality="many-to-one",
                                is_explicit=False,
                            ))

        return inferred

    def detect_junction_tables(
        self, relationships: list[Relationship]
    ) -> list[str]:
        fk_count: dict[str, list[Relationship]] = {}
        for rel in relationships:
            fk_count.setdefault(rel.from_table, []).append(rel)

        junctions = []
        for table, rels in fk_count.items():
            unique_targets = set(r.to_table for r in rels)
            if len(unique_targets) >= 2:
                junctions.append(table)

        return junctions

    def generate_mermaid(self, relationships: list[Relationship]) -> str:
        lines = ["erDiagram"]

        seen_tables: set[str] = set()
        for rel in relationships:
            seen_tables.add(rel.from_table)
            seen_tables.add(rel.to_table)

        for table in sorted(seen_tables):
            lines.append(f"    {table} {{")

            rels_from = [r for r in relationships if r.from_table == table]
            for rel in rels_from:
                lines.append(f"        string {rel.from_column} FK")

            lines.append("    }")

        for rel in relationships:
            if rel.cardinality == "many-to-one":
                lines.append("    " + rel.to_table + " ||--o{ " + rel.from_table + " : has")
            elif rel.cardinality == "one-to-one":
                lines.append("    " + rel.to_table + " ||--|| " + rel.from_table + " : has")
            elif rel.cardinality == "many-to-many":
                lines.append("    " + rel.to_table + " }o--o{ " + rel.from_table + " : has")

        return "\n".join(lines)
