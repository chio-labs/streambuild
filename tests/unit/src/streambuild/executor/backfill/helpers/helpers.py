from sqlglot import parse_one


def normalize_clickhouse_sql(sql: str) -> str:
    return parse_one(sql, dialect="clickhouse").sql(dialect="clickhouse")
