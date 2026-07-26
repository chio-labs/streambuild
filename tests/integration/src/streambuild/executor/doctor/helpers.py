from collections.abc import Callable
from typing import cast

from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.render.main.render_create_view_ddl import render_create_view_ddl


def _create_active_view(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    active_view_target_deployment_id: str | None,
    invalid_active_view_target_name: str | None,
) -> None:
    del invalid_active_view_target_name
    target_deployment_id: str = cast(str, active_view_target_deployment_id)
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name=f"tbl__orders_enriched__{target_deployment_id}",
        )
    )


def _leave_active_view_absent(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    active_view_target_deployment_id: str | None,
    invalid_active_view_target_name: str | None,
) -> None:
    del (
        clickhouse_client,
        clickhouse_database,
        active_view_target_deployment_id,
        invalid_active_view_target_name,
    )


def _create_invalid_active_view(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    active_view_target_deployment_id: str | None,
    invalid_active_view_target_name: str | None,
) -> None:
    del active_view_target_deployment_id
    target_name: str = cast(str, invalid_active_view_target_name)
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.{target_name} "
        "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
    )
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name=target_name,
        )
    )


DOCTOR_STATE_SETUP_BY_KIND: dict[str, Callable[..., None]] = {
    "active": _create_active_view,
    "missing": _leave_active_view_absent,
    "invalid": _create_invalid_active_view,
}


def prepare_doctor_state(
    *,
    setup_kind: str,
    clickhouse_client: Client,
    clickhouse_database: str,
    candidate_deployment_ids: tuple[str, ...],
    active_view_target_deployment_id: str | None,
    invalid_active_view_target_name: str | None,
) -> None:
    candidate_deployment_id: str
    for candidate_deployment_id in candidate_deployment_ids:
        clickhouse_client.command(
            "CREATE TABLE "
            f"{clickhouse_database}.tbl__orders_enriched__{candidate_deployment_id} "
            "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
        )
    DOCTOR_STATE_SETUP_BY_KIND[setup_kind](
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        active_view_target_deployment_id=active_view_target_deployment_id,
        invalid_active_view_target_name=invalid_active_view_target_name,
    )
