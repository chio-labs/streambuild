"""Expand authored Python macro calls with one invocation registry."""

from pathlib import Path

from streambuild.compiler.macros._helpers.expansion import expand_sql_body_macros
from streambuild.compiler.macros.models import MacroContext, MacroRegistry


def expand_macro_calls(
    *,
    sql: str,
    file_path: Path,
    registry: MacroRegistry,
    context: MacroContext,
    source_line: int = 1,
    source_column: int = 1,
) -> str:
    """Expand macro calls in one SQL body without loading modules."""

    return expand_sql_body_macros(
        sql=sql,
        file_path=file_path,
        registry=registry,
        context=context,
        source_line=source_line,
        source_column=source_column,
    )
