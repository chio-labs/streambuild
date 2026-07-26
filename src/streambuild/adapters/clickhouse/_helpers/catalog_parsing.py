"""Parse ClickHouse catalog details not exposed as dedicated system columns."""

from sqlglot import exp, parse_one

from streambuild.adapters.clickhouse.constants import (
    CLICKHOUSE_VIEW_ENGINE,
    EMPTY_KEY_EXPRESSIONS,
)


def parse_catalog_ddl_details(
    create_table_query: str,
) -> tuple[str | None, tuple[tuple[str, str], ...], str | None]:
    """Return TTL, settings, and materialized-view target from one catalog DDL."""

    expression: exp.Expr = parse_one(create_table_query, dialect="clickhouse")
    properties: exp.Properties | None = expression.args.get("properties")
    if properties is None:
        return None, (), None
    ttl_property: exp.MergeTreeTTL | None = properties.find(exp.MergeTreeTTL)
    settings_property: exp.SettingsProperty | None = properties.find(exp.SettingsProperty)
    target_property: exp.ToTableProperty | None = properties.find(exp.ToTableProperty)
    ttl: str | None = None
    if ttl_property is not None:
        ttl = ", ".join(
            ttl_expression.sql(dialect="clickhouse") for ttl_expression in ttl_property.expressions
        )
    settings: tuple[tuple[str, str], ...] = ()
    if settings_property is not None:
        settings = tuple(
            (
                setting.this.sql(dialect="clickhouse"),
                setting.expression.sql(dialect="clickhouse"),
            )
            for setting in settings_property.expressions
        )
    target_relation_name: str | None = None
    if target_property is not None:
        target_relation_name = target_property.this.name
    return ttl, settings, target_relation_name


def parse_sorting_key(value: str) -> tuple[str, ...]:
    """Parse the current ClickHouse sorting-key projection."""

    normalized: str = value.strip()
    if not normalized:
        return ()
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    return tuple(part.strip() for part in normalized.split(",") if part.strip())


def normalize_partition_key(value: str) -> str | None:
    """Normalize ClickHouse's empty partition-key sentinels."""

    return None if value in EMPTY_KEY_EXPRESSIONS else value


def normalize_catalog_query(value: str) -> str | None:
    """Normalize a relation query using the adapter's current SQL parser."""

    normalized: str = value.strip()
    if not normalized:
        return None
    return parse_one(normalized, dialect="clickhouse").sql(dialect="clickhouse")


def extract_source_relation_name(value: str) -> str | None:
    """Return the first source relation named by a catalog query."""

    normalized: str = value.strip()
    if not normalized:
        return None
    source: exp.Table | None = parse_one(normalized, dialect="clickhouse").find(exp.Table)
    return None if source is None else source.name


def extract_stable_binding(*, engine: str, as_select: str) -> str | None:
    """Preserve the characterized stable-view target extraction behavior."""

    marker: str = "FROM "
    if engine != CLICKHOUSE_VIEW_ENGINE or marker not in as_select:
        return None
    return as_select.split(marker, 1)[1].strip().split(".", 1)[1]
