"""Natural-language to SQL translation.

Two strategies:

1. ``llm_translate``  — real LLM-backed translation. Calls OpenAI or
   Anthropic over plain HTTP (``urllib``, no extra dependencies) when an
   API key is configured.
2. ``offline_translate`` — dependency-free rules-based parser that covers
   common English question shapes against the database's real table names.
"""

import asyncio
import json
import re
import urllib.request
from dataclasses import dataclass

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-3-5-haiku-20241022"

LLM_TIMEOUT = 25.0


@dataclass
class Translation:
    sql: str | None
    source: str  # "llm" or "offline"
    error: str | None = None


def _build_prompt(table_names: list[str]) -> str:
    quoted = ", ".join(f'"{t}"' for t in table_names)
    return (
        "You translate a user question into a single read-only SQL query. "
        "The database contains these tables: " + quoted + ".\n\n"
        "Rules:\n"
        "- Output ONLY the SQL statement. No explanations, no markdown.\n"
        "- Use SELECT (or WITH ... SELECT). Never INSERT/UPDATE/DELETE/DROP.\n"
        "- Quote identifiers that need quoting, values must be quoted properly.\n"
        "- Return plain text SQL ending with a newline."
    )


def _extract_sql(response: str) -> str | None:
    text = response.strip()
    if not text:
        return None
    # strip triple-backtick fences (with or without a language tag)
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        # if the model wrapped the answer in prose, grab the first statement
        for ln in text.splitlines():
            ln = ln.strip()
            if re.match(r"^(SELECT|WITH)\b", ln, re.IGNORECASE):
                text = ln
                break
    text = text.rstrip(";").strip()
    if re.match(r"^(SELECT|WITH)\b", text, re.IGNORECASE):
        return text
    return None


def _call_openai(api_key: str, prompt: str, question: str, model: str) -> str:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": question},
        ],
        "temperature": 0,
    }
    req = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _call_anthropic(api_key: str, prompt: str, question: str, model: str) -> str:
    body = {
        "model": model,
        "max_tokens": 512,
        "system": prompt,
        "messages": [{"role": "user", "content": question}],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data.get("content", [])
    return "".join(block.get("text", "") for block in content)


async def llm_translate(
    question: str,
    table_names: list[str],
    *,
    openai_key: str | None = None,
    anthropic_key: str | None = None,
    openai_model: str = DEFAULT_OPENAI_MODEL,
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL,
) -> Translation:
    """Translate via a real LLM API call (OpenAI preferred, then Anthropic)."""
    prompt = _build_prompt(table_names)

    if openai_key:
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(_call_openai, openai_key, prompt, question, openai_model),
                timeout=LLM_TIMEOUT,
            )
            sql = _extract_sql(raw)
            if sql:
                return Translation(sql=sql, source="llm")
            return Translation(sql=None, source="llm", error="LLM returned no usable SQL")
        except Exception as e:  # network, timeout, bad response
            return Translation(sql=None, source="llm", error=str(e))

    if anthropic_key:
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(_call_anthropic, anthropic_key, prompt, question, anthropic_model),
                timeout=LLM_TIMEOUT,
            )
            sql = _extract_sql(raw)
            if sql:
                return Translation(sql=sql, source="llm")
            return Translation(sql=None, source="llm", error="LLM returned no usable SQL")
        except Exception as e:
            return Translation(sql=None, source="llm", error=str(e))

    return Translation(sql=None, source="llm", error="No API key configured")


def offline_translate(question: str, table_names: list[str]) -> Translation:
    """Rule-based fallback. English-only patterns, matched against real tables."""
    table_map = {t.lower(): t for t in table_names}
    q = question.lower().strip()

    def table_match(words: tuple[str, ...]) -> tuple[str, list[str]] | None:
        """Return (real_name, matched_words) if any consecutive table matches."""
        if not words:
            return None
        for i in range(len(words)):
            for size in (2, 1):
                if i + size > len(words):
                    continue
                chunk = " ".join(words[i : i + size])
                candidates = {chunk}
                folded = chunk.replace("_", "")
                candidates.add(folded)
                # singular/plural tolerance ("user" -> "users", "users" -> "user")
                candidates.add(chunk + "s")
                if size == 1 and chunk.endswith("s"):
                    candidates.add(chunk[:-1])
                for cand in candidates:
                    if cand in table_map:
                        return table_map[cand], list(words[i : i + size])
        return None

    words = re.findall(r"[\w_]+", q)

    # "how many <table>." / "count of <table>." / "how many <table> are there"
    m = re.search(r"\b(?:how many|count|number of)\b\s+([\w\s]+?)\s*$", q)
    if m:
        hit = table_match(tuple(m.group(1).split()))
        if hit:
            tbl = hit[0]
            return Translation(sql=f'SELECT COUNT(*) AS count FROM "{tbl}"', source="offline")

    # "top N <col> of <table>" / "highest/lowest/most/least ... <col> in <table>"
    m = re.search(
        r"\b(top|best|worst|highest|lowest|most expensive|least expensive|max|min)\b\s*"
        r"(\d+)?\s*([\w_]+?)\s+(?:in|of|from)\s+([\w\s]+)",
        q,
    )
    if m:
        order, num_s, col_part, tbl_part = m.groups()
        hit = table_match(tuple(tbl_part.split()))
        if hit:
            tbl = hit[0]
            col_cand = col_part.strip()
            limit = int(num_s) if num_s else 10
            direction = "ASC" if order in ("lowest", "least expensive", "min") else "DESC"
            return Translation(
                sql=f'SELECT * FROM "{tbl}" ORDER BY "{col_cand}" {direction} LIMIT {limit}',
                source="offline",
            )

    # "show/list/get/select ... <col> from <table>" or "select * from <table>"
    m = re.search(r"\bfrom\s+([\w\s]+)", q)
    if m:
        hit = table_match(tuple(m.group(2).split()))
        if hit:
            tbl = hit[0]
            return Translation(sql=f'SELECT * FROM "{tbl}" LIMIT 100', source="offline")

    # "<table> where <col> = <value>"
    m = re.search(r"\bwhere\b\s+([\w_]+)\s*[=:]\s*['\"]?([\w\s.,%]+?)['\"]?$", q)
    if m:
        col_cand, val = m.groups()
        hit = table_match(tuple(words))
        if hit:
            tbl = hit[0]
            if re.fullmatch(r"\d+(\.\d+)?", val.strip()):
                return Translation(
                    sql=f'SELECT * FROM "{tbl}" WHERE "{col_cand}" = {val.strip()} LIMIT 100',
                    source="offline",
                )
            return Translation(
                sql=f'SELECT * FROM "{tbl}" WHERE "{col_cand}" = \'{val.strip()}\' LIMIT 100',
                source="offline",
            )

    # table mentioned at all → return the table as a fallback listing
    if words:
        hit = table_match(tuple(words))
        if hit:
            tbl = hit[0]
            return Translation(sql=f'SELECT * FROM "{tbl}" LIMIT 100', source="offline")

    return Translation(sql=None, source="offline")


async def translate(
    question: str,
    table_names: list[str],
    *,
    openai_key: str | None = None,
    anthropic_key: str | None = None,
) -> Translation:
    """Prefer the LLM path when a key is available, otherwise use the parser."""
    llm = await llm_translate(
        question,
        table_names,
        openai_key=openai_key,
        anthropic_key=anthropic_key,
    )
    if llm.sql:
        return llm

    offline = offline_translate(question, table_names)
    if offline.sql:
        return offline

    if llm.error and llm.error != "No API key configured":
        return Translation(sql=None, source="llm", error=llm.error)
    return Translation(sql=None, source="offline")