import threading
import time

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterConnectionConfig, AdapterQueryCancellation
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.integration.src.streambuild.adapters.clickhouse._test_types import (
    QueryCancellationIntegrationTestCase,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        QueryCancellationIntegrationTestCase(
            description="long-running query disappears after exact cancellation",
            query_id="streambuild-integration-cancellation",
            unrelated_query_id="streambuild-integration-cancellation-unrelated",
            statement=("SELECT sleepEachRow(0.01) FROM numbers(1000) SETTINGS max_block_size = 1"),
            expected_query_found=True,
            expected_termination_confirmed=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_long_running_owned_query_when_cancelling_then_query_leaves_system_processes(
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    test_case: QueryCancellationIntegrationTestCase,
) -> None:
    config: AdapterConnectionConfig = AdapterConnectionConfig(
        host=clickhouse_connection_settings.host,
        port=clickhouse_connection_settings.port,
        username=clickhouse_connection_settings.username,
        password=clickhouse_connection_settings.password,
    )
    worker: AdapterConnection = ClickHouseAdapter().connect(config)
    unrelated_worker: AdapterConnection = ClickHouseAdapter().connect(config)
    canceller: AdapterConnection = ClickHouseAdapter().connect(config)
    query_finished: threading.Event = threading.Event()
    unrelated_query_finished: threading.Event = threading.Event()
    worker_errors: list[AdapterError] = []

    def run_query() -> None:
        try:
            _ = worker.execute_workflow_query(
                statement=test_case.statement,
                query_id=test_case.query_id,
            )
        except AdapterError as error:
            worker_errors.append(error)
        finally:
            query_finished.set()

    def run_unrelated_query() -> None:
        try:
            _ = unrelated_worker.execute_workflow_query(
                statement=test_case.statement,
                query_id=test_case.unrelated_query_id,
            )
        except AdapterError:
            pass
        finally:
            unrelated_query_finished.set()

    thread: threading.Thread = threading.Thread(target=run_query, daemon=True)
    unrelated_thread: threading.Thread = threading.Thread(target=run_unrelated_query, daemon=True)
    thread.start()
    unrelated_thread.start()
    time.sleep(0.2)
    assert canceller.load_statement_progress(query_id=test_case.query_id) is not None
    assert canceller.load_statement_progress(query_id=test_case.unrelated_query_id) is not None

    cancellation: AdapterQueryCancellation = canceller.cancel_workflow_query(
        query_id=test_case.query_id
    )

    assert query_finished.wait(timeout=5.0)
    assert cancellation.supported is True
    assert cancellation.query_found is test_case.expected_query_found
    assert cancellation.termination_confirmed is test_case.expected_termination_confirmed
    assert canceller.load_statement_progress(query_id=test_case.query_id) is None
    assert canceller.load_statement_progress(query_id=test_case.unrelated_query_id) is not None
    assert worker_errors
    _ = canceller.cancel_workflow_query(query_id=test_case.unrelated_query_id)
    assert unrelated_query_finished.wait(timeout=5.0)
    worker.close()
    unrelated_worker.close()
    canceller.close()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
