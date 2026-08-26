FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY src/ src/

RUN useradd --create-home mcpuser
USER mcpuser

ENTRYPOINT ["python", "-m", "src"]
