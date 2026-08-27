FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .
COPY mcp_database_universal/ mcp_database_universal/

RUN useradd --create-home mcpuser
USER mcpuser

ENTRYPOINT ["python", "-m", "mcp_database_universal"]
