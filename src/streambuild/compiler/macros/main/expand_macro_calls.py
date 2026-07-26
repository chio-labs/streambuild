"""Expansion entrypoint for authored Python SQL macros."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.macros._helpers.expansion import (
    expand_sql_body_macros,
)
from streambuild.compiler.macros._helpers.registry import (
    load_project_macros,
)


def expand_project_sql_macros(*, sql: str, file_path: Path) -> str:
    """Expand authored Python macros for one SQL file body."""

    return expand_sql_body_macros(
        sql=sql,
        file_path=file_path,
        loaded_macros=load_project_macros(file_path),
    )
