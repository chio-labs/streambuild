from collections.abc import Sequence

from clickhouse_connect.driver.client import Client


def build_live_shadow_debug_message(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    raw_table_name: str,
    staged_table_name: str,
    error: AssertionError,
) -> str:
    staged_mv_name: str = staged_table_name.replace("tbl__", "mv__", 1)
    live_table_name: str = staged_table_name.rsplit("__", maxsplit=1)[0]
    raw_count: int = _query_table_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=raw_table_name,
    )
    staged_count: int = _query_table_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=staged_table_name,
    )
    latest_raw_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT _replay_partition, _replay_offset, _replay_timestamp FROM "
        f"{clickhouse_database}.{raw_table_name} "
        "ORDER BY _replay_partition DESC, _replay_offset DESC LIMIT 5"
    ).result_rows
    latest_staged_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id, _replay_timestamp FROM {clickhouse_database}.{staged_table_name} "
        "ORDER BY _replay_timestamp DESC, order_id DESC LIMIT 5"
    ).result_rows
    live_count: int | None = _query_optional_table_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=live_table_name,
    )
    staged_mv_exists: bool = _table_exists(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=staged_mv_name,
    )
    staged_mv_ddl: str | None = None
    if staged_mv_exists:
        staged_mv_ddl = str(
            clickhouse_client.query(
                f"SHOW CREATE TABLE {clickhouse_database}.{staged_mv_name}"
            ).result_rows[0][0]
        )
    return (
        f"{error}. raw_count={raw_count}, staged_count={staged_count}, "
        f"live_count={live_count}, staged_mv_exists={staged_mv_exists}, "
        f"latest_raw_rows={tuple(latest_raw_rows)}, "
        f"latest_staged_rows={tuple(latest_staged_rows)}, "
        f"staged_mv_ddl={staged_mv_ddl!r}"
    )


def _query_table_count(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    table_name: str,
) -> int:
    return int(
        clickhouse_client.query(
            f"SELECT count() FROM {clickhouse_database}.{table_name}"
        ).result_rows[0][0]
    )


def _query_optional_table_count(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    table_name: str,
) -> int | None:
    if not _table_exists(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=table_name,
    ):
        return None
    return _query_table_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=table_name,
    )


def _table_exists(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    table_name: str,
) -> bool:
    return bool(
        clickhouse_client.query(
            "SELECT count() FROM system.tables "
            f"WHERE database = '{clickhouse_database}' AND name = '{table_name}'"
        ).result_rows[0][0]
    )
