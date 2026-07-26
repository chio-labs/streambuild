"""Render CREATE VIEW DDL for stable logical relations."""


def render_create_view_ddl(
    *,
    database: str,
    view_name: str,
    target_table_name: str,
) -> str:
    """Render a stable logical view over a physical managed table."""

    return (
        f"CREATE OR REPLACE VIEW {database}.{view_name} AS\n"
        f"SELECT * FROM {database}.{target_table_name}"
    )
