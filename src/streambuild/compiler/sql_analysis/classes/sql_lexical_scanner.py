"""Shared SQL lexical scanning behavior for compiler-owned syntaxes."""

from streambuild.compiler.sql_analysis._helpers.scanning import (
    find_matching_parenthesis,
    find_next_unquoted_character,
)


class SqlLexicalScanner:
    """Find syntax outside ClickHouse comments and quoted text."""

    @staticmethod
    def find_matching_parenthesis(*, sql: str, open_index: int, context: str) -> int:
        """Return the close index matching one opening parenthesis."""

        return find_matching_parenthesis(
            sql=sql,
            open_index=open_index,
            context=context,
        )

    @staticmethod
    def find_next_unquoted_character(*, sql: str, character: str, start: int) -> int | None:
        """Find one character outside comments and quoted text."""

        return find_next_unquoted_character(
            sql=sql,
            character=character,
            start=start,
        )
