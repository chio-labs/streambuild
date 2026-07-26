import pytest
from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.render.main.render_create_view_ddl import render_create_view_ddl
from streambuild.executor.doctor.main.execute_doctor import execute_doctor
from streambuild.executor.doctor.models import ActiveViewStatus, DoctorRequest, DoctorResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.main.connect_clickhouse import (
    connect_clickhouse,
)
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.doctor._test_types import (
    ExecuteDoctorIntegrationTestCase,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteDoctorIntegrationTestCase(
            description="reports active view healthy when one binding exists",
            active_view_target_deployment_id="dep_a",
            candidate_deployment_ids=("dep_a", "dep_b"),
            invalid_active_view_target_name=None,
            expected_state_kind="active_view_present",
            expected_active_deployment_id="dep_a",
            expected_candidate_deployment_ids=("dep_a", "dep_b"),
        ),
        ExecuteDoctorIntegrationTestCase(
            description="reports recoverable missing logical view when one candidate exists",
            active_view_target_deployment_id=None,
            candidate_deployment_ids=("dep_a",),
            invalid_active_view_target_name=None,
            expected_state_kind="logical_view_missing",
            expected_active_deployment_id=None,
            expected_candidate_deployment_ids=("dep_a",),
        ),
        ExecuteDoctorIntegrationTestCase(
            description="reports ambiguous missing logical view when many candidates exist",
            active_view_target_deployment_id=None,
            candidate_deployment_ids=("dep_a", "dep_b"),
            invalid_active_view_target_name=None,
            expected_state_kind="logical_view_missing",
            expected_active_deployment_id=None,
            expected_candidate_deployment_ids=("dep_a", "dep_b"),
        ),
        ExecuteDoctorIntegrationTestCase(
            description=(
                "reports invalid active view when stable view points to a non-deployment table"
            ),
            active_view_target_deployment_id=None,
            candidate_deployment_ids=(),
            invalid_active_view_target_name="tbl__orders_enriched_manual",
            expected_state_kind="invalid_active_view",
            expected_active_deployment_id=None,
            expected_candidate_deployment_ids=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_state_when_doctoring_then_it_reports_expected_active_view_status(
    test_case: ExecuteDoctorIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    candidate_deployment_id: str
    for candidate_deployment_id in test_case.candidate_deployment_ids:
        clickhouse_client.command(
            "CREATE TABLE "
            f"{clickhouse_database}.tbl__orders_enriched__{candidate_deployment_id} "
            "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
        )
    if test_case.active_view_target_deployment_id is not None:
        clickhouse_client.command(
            render_create_view_ddl(
                database=clickhouse_database,
                view_name="tbl__orders_enriched",
                target_table_name=(
                    f"tbl__orders_enriched__{test_case.active_view_target_deployment_id}"
                ),
            )
        )
    if test_case.invalid_active_view_target_name is not None:
        clickhouse_client.command(
            "CREATE TABLE "
            f"{clickhouse_database}.{test_case.invalid_active_view_target_name} "
            "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
        )
        clickhouse_client.command(
            render_create_view_ddl(
                database=clickhouse_database,
                view_name="tbl__orders_enriched",
                target_table_name=test_case.invalid_active_view_target_name,
            )
        )

    managed_client: ClickHouseClient = connect_clickhouse(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        result: DoctorResult = execute_doctor(
            request=DoctorRequest(default_database=clickhouse_database),
            client=managed_client,
        )
    finally:
        managed_client.close()

    status: ActiveViewStatus = result.active_views[0]
    assert status.table_name == "tbl__orders_enriched"
    assert status.state_kind == test_case.expected_state_kind
    assert status.active_deployment_id == test_case.expected_active_deployment_id
    assert status.candidate_deployment_ids == test_case.expected_candidate_deployment_ids
