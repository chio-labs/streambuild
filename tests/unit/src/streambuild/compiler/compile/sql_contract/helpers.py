from streambuild.compiler.compile.models import Column
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer


def build_expected_columns(*column_definitions: tuple[str, str]) -> tuple[Column, ...]:
    return tuple(Column(name=name, type=column_type) for name, column_type in column_definitions)


def build_sql_analyzer() -> SqlModelAnalyzer:
    return SqlModelAnalyzer(dialect="clickhouse")
