"""Public entrypoint for lexical macro call discovery."""

from __future__ import annotations

from streambuild.compiler.macros._helpers.expansion import find_macro_call_names_impl


def find_macro_call_names(sql: str) -> tuple[str, ...]:
    """Return unique authored macro call names outside comments and quoted text."""

    return find_macro_call_names_impl(sql)
