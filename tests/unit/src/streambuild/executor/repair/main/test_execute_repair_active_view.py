import pytest

from streambuild.adapter.exceptions import AdapterCapabilityError, AdapterResultError
from streambuild.adapter.models import AdapterBindingReplacementRequest, AdapterStableBinding
from streambuild.executor.repair.main.execute_repair_active_view import execute_repair_active_view
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.repair.main._test_types import (
    RepairBindingResultTestCase,
    RepairBindingTestCase,
    RepairCapabilityTestCase,
)
from tests.unit.src.streambuild.executor.repair.main.helpers import (
    WrongRepairBindingAdapterConnection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RepairBindingTestCase(
            description="replaces exactly one requested stable binding",
            request=RepairActiveViewRequest(
                default_database="analytics",
                table_name="tbl__orders_enriched",
                deployment_id="dep_b",
            ),
            expected_binding_request=AdapterBindingReplacementRequest(
                bindings=(
                    AdapterStableBinding(
                        database="analytics",
                        logical_name="tbl__orders_enriched",
                        physical_name="tbl__orders_enriched__dep_b",
                    ),
                )
            ),
            expected_result=RepairActiveViewResult(
                table_name="tbl__orders_enriched",
                target_table_name="tbl__orders_enriched__dep_b",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repair_target_when_rebinding_then_it_uses_neutral_binding_replacement(
    test_case: RepairBindingTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

    result: RepairActiveViewResult = execute_repair_active_view(
        request=test_case.request,
        client=connection,
    )

    assert connection.binding_requests == [test_case.expected_binding_request]
    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        RepairCapabilityTestCase(
            description="rejects repair before writes when stable bindings are unsupported",
            expected_error_fragment=(
                "Adapter 'clickhouse' does not support stable logical bindings"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_without_stable_bindings_when_repairing_then_it_fails_before_writes(
    test_case: RepairCapabilityTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        stable_logical_bindings=False
    )

    with pytest.raises(AdapterCapabilityError, match=test_case.expected_error_fragment):
        execute_repair_active_view(
            request=RepairActiveViewRequest(
                default_database="analytics",
                table_name="tbl__orders_enriched",
                deployment_id="dep_b",
            ),
            client=connection,
        )

    assert connection.binding_requests == []


@pytest.mark.parametrize(
    "test_case",
    [
        RepairBindingResultTestCase(
            description="rejects a binding result for the wrong deployment",
            request=RepairActiveViewRequest(
                default_database="analytics",
                table_name="tbl__orders_enriched",
                deployment_id="dep_b",
            ),
            returned_bindings=(
                AdapterStableBinding(
                    database="analytics",
                    logical_name="tbl__orders_enriched",
                    physical_name="tbl__orders_enriched__dep_a",
                ),
            ),
            expected_error_fragment=(
                "Adapter returned a binding that did not match the repair request"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_returns_wrong_binding_when_repairing_then_it_rejects_success(
    test_case: RepairBindingResultTestCase,
) -> None:
    connection: WrongRepairBindingAdapterConnection = WrongRepairBindingAdapterConnection(
        test_case.returned_bindings
    )

    with pytest.raises(AdapterResultError, match=test_case.expected_error_fragment):
        execute_repair_active_view(request=test_case.request, client=connection)

    assert len(connection.binding_requests) == 1
