"""Rename relational control-store tables created before the SQLTide rename."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from sqltide.auth.constants import (
    CONTROL_STORE_TABLE_PREFIX,
    STREAMBUILD_CONTROL_STORE_TABLE_PREFIX,
)


def rename_streambuild_tables(engine: Engine) -> None:
    """Rename every pre-rename table whose SQLTide name is still free."""

    with engine.begin() as connection:
        existing: frozenset[str] = frozenset(inspect(connection).get_table_names())
        for name in sorted(existing):
            if not name.startswith(STREAMBUILD_CONTROL_STORE_TABLE_PREFIX):
                continue
            renamed: str = CONTROL_STORE_TABLE_PREFIX + name.removeprefix(
                STREAMBUILD_CONTROL_STORE_TABLE_PREFIX
            )
            if renamed in existing:
                continue
            connection.execute(text(f'ALTER TABLE "{name}" RENAME TO "{renamed}"'))
