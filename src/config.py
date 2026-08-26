"""Configuration for MCP Database Server."""

import os
from dataclasses import dataclass


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
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Example: sqlite:///path/to/db.db"
            )

        return cls(
            url=url,
            read_only=os.environ.get("DATABASE_READ_ONLY", "true").lower() == "true",
            write_enabled=os.environ.get("DATABASE_WRITE_ENABLED", "false").lower() == "true",
            max_rows=int(os.environ.get("DATABASE_MAX_ROWS", "1000")),
            max_query_time=int(os.environ.get("DATABASE_MAX_QUERY_TIME", "30")),
            max_output_bytes=int(os.environ.get("DATABASE_MAX_OUTPUT_BYTES", "50000")),
            sample_size=int(os.environ.get("DATABASE_SAMPLE_SIZE", "5")),
            profile_top_n=int(os.environ.get("DATABASE_PROFILE_TOP_N", "10")),
            openai_key=os.environ.get("OPENAI_API_KEY") or None,
            anthropic_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        )

    def is_effectively_read_only(self) -> bool:
        return self.read_only and not self.write_enabled
