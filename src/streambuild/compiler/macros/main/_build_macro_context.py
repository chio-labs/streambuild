"""Build one immutable macro execution context."""

from collections.abc import Mapping

from streambuild.compiler.macros.models import MacroContext


def build_macro_context(
    *,
    adapter_name: str,
    dialect: str,
    target_name: str | None,
    database: str | None,
    schema: str | None,
    virtual_environments: bool,
    variables: Mapping[str, object],
) -> MacroContext:
    """Build one connection-free deeply immutable macro context."""

    return MacroContext(
        adapter_name=adapter_name,
        dialect=dialect,
        target_name=target_name,
        database=database,
        schema=schema,
        virtual_environments=virtual_environments,
        variables=variables,
    )
