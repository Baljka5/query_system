from sqlglot import parse_one, errors

DIALECT_MAP = {
    "postgres": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "mssql": "tsql",
    "clickhouse": "clickhouse",
    "other": "mysql",
}

class SQLSyntaxError(Exception):
    pass

def validate_sql(sql_text: str, db_type: str) -> str:
    sql_text = (sql_text or "").strip()
    if not sql_text:
        raise SQLSyntaxError("Empty SQL.")
    dialect = DIALECT_MAP.get((db_type or "other"), "mysql")
    try:
        parse_one(sql_text, read=dialect)
    except errors.ParseError as e:
        raise SQLSyntaxError(str(e)) from e
    return dialect
