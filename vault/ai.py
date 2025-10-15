# vault/ai.py
import os
import re
import requests

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()  # "ollama" | "openai" | ""

# Deterministic options
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "200"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.0"))  # <= 0.0
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "1.0"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_SEED = int(os.getenv("OLLAMA_SEED", "7"))  # << seed

SESSION = requests.Session()


def _strip_sql_fence(text: str) -> str:
    if not text: return ""
    m = re.search(r"```(?:sql)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    text = (m.group(1) if m else text).strip()
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", text)
    return text


def _dialect_name(db_type: str) -> str:
    return {"mysql": "MySQL", "postgres": "PostgreSQL", "sqlite": "SQLite", "mssql": "SQL Server",
            "clickhouse": "ClickHouse", "other": "ANSI SQL"}.get((db_type or "other").lower(), "ANSI SQL")


def _allowed_text(allowed_kinds):
    if "dangerous" in allowed_kinds: return "You may emit ANY statements."
    if "modify" in allowed_kinds:    return "You may emit only SELECT, INSERT, UPDATE (no DELETE, no DDL)."
    return "You MUST emit ONLY SELECT queries (no INSERT/UPDATE/DELETE/DDL)."


def _system_prompt(db_type: str, allowed_kinds):
    return ("You are a senior SQL generator. "
            f"Target dialect: {_dialect_name(db_type)}. "
            "Return ONLY executable SQL. No comments, no markdown, no explanations. "
            f"{_allowed_text(allowed_kinds)} "
            "Always alias subqueries. Output a single statement.")


def _user_prompt(ask: str, schema: str) -> str:
    base = f"Natural language request:\n{ask or ''}\n"
    if schema: base += f"\nHelpful schema description (optional):\n{schema}\n"
    return base + "\nReturn only the SQL."


def _call_openai(messages):
    if not OPENAI_API_KEY: raise RuntimeError("OpenAI provider is not configured (OPENAI_API_KEY missing).")
    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {"model": OPENAI_MODEL, "messages": messages, "temperature": 0.0}  # deterministic
    r = SESSION.post(url, json=payload, headers=headers, timeout=60);
    r.raise_for_status()
    data = r.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content: raise RuntimeError("OpenAI returned empty response.")
    return content


def _call_ollama(messages):
    if not OLLAMA_BASE_URL: raise RuntimeError("Ollama provider is not configured (OLLAMA_BASE_URL missing).")
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "options": {
            "temperature": OLLAMA_TEMPERATURE,
            "top_p": OLLAMA_TOP_P,
            "num_predict": OLLAMA_NUM_PREDICT,
            "num_ctx": OLLAMA_NUM_CTX,
            "seed": OLLAMA_SEED,  # << deterministic
        },
        "stream": False,
    }
    r = SESSION.post(url, json=payload, timeout=120);
    r.raise_for_status()
    data = r.json()
    content = (data.get("message") or {}).get("content") or data.get("response")
    if not content and isinstance(data.get("messages"), list) and data["messages"]:
        content = data["messages"][-1].get("content")
    if not content: raise RuntimeError("Ollama returned empty response.")
    return content


def _provider_call(messages):
    provider = AI_PROVIDER if AI_PROVIDER in {"openai", "ollama"} else ("openai" if OPENAI_API_KEY else "ollama")
    return _call_openai(messages) if provider == "openai" else _call_ollama(messages)


def ai_generate_sql(ask: str, db_type: str, schema: str, allowed_kinds, examples=None) -> str:
    messages = [{"role": "system", "content": _system_prompt(db_type, allowed_kinds)}]
    for ex in (examples or []):
        nl = (ex.get("nl") or "").strip();
        sc = (ex.get("schema") or "").strip();
        sql = (ex.get("sql") or "").strip()
        if not (nl and sql): continue
        messages.append({"role": "user", "content": _user_prompt(nl, sc)})
        messages.append({"role": "assistant", "content": sql})
    messages.append({"role": "user", "content": _user_prompt(ask, schema)})
    return _strip_sql_fence(_provider_call(messages))


def ai_fix_sql(bad_sql: str, db_type: str, allowed_kinds, error_msg: str) -> str:
    messages = [
        {"role": "system", "content": _system_prompt(db_type, allowed_kinds)},
        {"role": "user",
         "content": f"The following SQL is INVALID for {_dialect_name(db_type)}.\nParser error: {error_msg}\nReturn ONLY the corrected SQL. No comments.\n\n{bad_sql}"},
    ]
    return _strip_sql_fence(_provider_call(messages))
