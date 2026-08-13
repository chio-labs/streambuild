"""Behavior tests for one sequential sensor dispatch pass."""

import pytest

from streambuild.sensors.classes.sensor_dispatcher import SensorDispatcher
from streambuild.sensors.models import (
    PollingTickState,
    SensorDispatchSummary,
    SensorRegistry,
    TickAttemptState,
)
from streambuild.sensors.types import SensorOverrideStatus, SensorTickStatus
from tests.unit.src.streambuild.events.helpers import build_node_result_observation
from tests.unit.src.streambuild.sensors.classes._test_types import (
    DeadLetterActionTestCase,
    DispatcherScenarioTestCase,
)
from tests.unit.src.streambuild.sensors.classes.helpers import (
    EPOCH_POSITION,
    ROW_POSITION,
    backoff_sensor,
    failing_sensor,
    polling_lag,
    prod_only_sensor,
    skipping_sensor,
    stopped_sensor,
    succeeding_sensor,
)
from tests.unit.src.streambuild.sensors.helpers import (
    FAKE_WAREHOUSE_NOW,
    FakeSensorStateRepository,
    build_loaded_sensor,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DispatcherScenarioTestCase(
            description="fresh failing audit event evaluates and advances the checkpoint",
            sensor=build_loaded_sensor(declaration=succeeding_sensor),
            checkpoints={("succeeding_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            expected_tick_statuses=("started", "succeeded"),
            expected_advanced_count=1,
            expected_summary=SensorDispatchSummary(evaluated=1, succeeded=1),
        ),
        DispatcherScenarioTestCase(
            description="handler failure records a failed tick and blocks the checkpoint",
            sensor=build_loaded_sensor(declaration=failing_sensor),
            checkpoints={("failing_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            expected_tick_statuses=("started", "failed"),
            expected_advanced_count=0,
            expected_summary=SensorDispatchSummary(evaluated=1, failed=1),
        ),
        DispatcherScenarioTestCase(
            description="exhausted attempts dead-letter the event and unblock the stream",
            sensor=build_loaded_sensor(declaration=failing_sensor),
            checkpoints={("failing_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            attempt_states={
                ("failing_sensor", "result-1"): TickAttemptState(
                    failed_attempts=2,
                    last_failed_at="2024-01-01 00:00:02.000",
                    last_error_message="RuntimeError: boom",
                    resolved=False,
                )
            },
            expected_tick_statuses=("dead_lettered",),
            expected_advanced_count=1,
            expected_summary=SensorDispatchSummary(dead_lettered=1),
        ),
        DispatcherScenarioTestCase(
            description="pending backoff blocks the stream without re-evaluating",
            sensor=build_loaded_sensor(declaration=backoff_sensor),
            checkpoints={("backoff_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            attempt_states={
                ("backoff_sensor", "result-1"): TickAttemptState(
                    failed_attempts=1,
                    last_failed_at=FAKE_WAREHOUSE_NOW,
                    last_error_message="RuntimeError: boom",
                    resolved=False,
                )
            },
            expected_tick_statuses=(),
            expected_advanced_count=0,
            expected_summary=SensorDispatchSummary(),
        ),
        DispatcherScenarioTestCase(
            description="resolved events advance without new ticks",
            sensor=build_loaded_sensor(declaration=succeeding_sensor),
            checkpoints={("succeeding_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            attempt_states={
                ("succeeding_sensor", "result-1"): TickAttemptState(
                    failed_attempts=0,
                    last_failed_at=None,
                    last_error_message=None,
                    resolved=True,
                )
            },
            expected_tick_statuses=(),
            expected_advanced_count=1,
            expected_summary=SensorDispatchSummary(),
        ),
        DispatcherScenarioTestCase(
            description="first enable initializes the checkpoint at the newest observation",
            sensor=build_loaded_sensor(declaration=succeeding_sensor),
            node_results=(build_node_result_observation(),),
            newest_position=ROW_POSITION,
            expected_tick_statuses=(),
            expected_advanced_count=1,
            expected_summary=SensorDispatchSummary(),
        ),
        DispatcherScenarioTestCase(
            description="sensors stopped by declared default are not dispatched",
            sensor=build_loaded_sensor(declaration=stopped_sensor),
            checkpoints={("stopped_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            expected_tick_statuses=(),
            expected_advanced_count=0,
            expected_summary=SensorDispatchSummary(),
        ),
        DispatcherScenarioTestCase(
            description="a running override enables a sensor stopped in code",
            sensor=build_loaded_sensor(declaration=stopped_sensor),
            checkpoints={("stopped_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            overrides={"stopped_sensor": SensorOverrideStatus.RUNNING},
            expected_tick_statuses=("started", "succeeded"),
            expected_advanced_count=1,
            expected_summary=SensorDispatchSummary(evaluated=1, succeeded=1),
        ),
        DispatcherScenarioTestCase(
            description="skip reasons resolve events with a recorded skipped tick",
            sensor=build_loaded_sensor(declaration=skipping_sensor),
            checkpoints={("skipping_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            expected_tick_statuses=("started", "skipped"),
            expected_advanced_count=1,
            expected_summary=SensorDispatchSummary(evaluated=1, skipped=1),
        ),
        DispatcherScenarioTestCase(
            description="target-filtered events advance without evaluation",
            sensor=build_loaded_sensor(declaration=prod_only_sensor),
            checkpoints={("prod_only_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(target_identity="staging"),),
            expected_tick_statuses=(),
            expected_advanced_count=1,
            expected_summary=SensorDispatchSummary(),
        ),
        DispatcherScenarioTestCase(
            description="a lease held elsewhere skips the entire pass",
            sensor=build_loaded_sensor(declaration=succeeding_sensor),
            checkpoints={("succeeding_sensor", "node_results"): EPOCH_POSITION},
            node_results=(build_node_result_observation(),),
            lease_acquired=False,
            expected_tick_statuses=(),
            expected_advanced_count=0,
            expected_summary=SensorDispatchSummary(lease_acquired=False),
        ),
        DispatcherScenarioTestCase(
            description="due polling sensors evaluate and persist their cursor",
            sensor=build_loaded_sensor(declaration=polling_lag),
            expected_tick_statuses=("started", "succeeded"),
            expected_advanced_count=0,
            expected_summary=SensorDispatchSummary(evaluated=1, succeeded=1),
        ),
        DispatcherScenarioTestCase(
            description="polling sensors within their interval are not evaluated",
            sensor=build_loaded_sensor(declaration=polling_lag),
            polling_states={
                "polling_lag": PollingTickState(
                    last_started_at=FAKE_WAREHOUSE_NOW,
                    last_success_at=FAKE_WAREHOUSE_NOW,
                    cursor="41",
                )
            },
            expected_tick_statuses=(),
            expected_advanced_count=0,
            expected_summary=SensorDispatchSummary(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_when_dispatching_once_then_ticks_and_checkpoints_match(
    test_case: DispatcherScenarioTestCase,
) -> None:
    repository: FakeSensorStateRepository = FakeSensorStateRepository(
        checkpoints=test_case.checkpoints,
        node_results=test_case.node_results,
        invocations=test_case.invocations,
        previous_statuses=test_case.previous_statuses,
        attempt_states=test_case.attempt_states,
        overrides=test_case.overrides,
        polling_states=test_case.polling_states,
        newest_position=test_case.newest_position,
        lease_acquired=test_case.lease_acquired,
    )
    dispatcher: SensorDispatcher = SensorDispatcher(repository=repository)
    registry: SensorRegistry = SensorRegistry(sensors={test_case.sensor.name: test_case.sensor})

    summary: SensorDispatchSummary = dispatcher.dispatch_once(registry=registry, target="prod")

    assert summary == test_case.expected_summary
    assert tuple(tick.status for tick in repository.recorded_ticks) == (
        test_case.expected_tick_statuses
    )
    assert len(repository.advanced) == test_case.expected_advanced_count


@pytest.mark.parametrize(
    "test_case",
    [
        DeadLetterActionTestCase(
            description="retrying a dead letter re-evaluates and records the outcome",
            sensor=build_loaded_sensor(declaration=succeeding_sensor),
            node_results=(build_node_result_observation(),),
            attempt_states={
                ("succeeding_sensor", "result-1"): TickAttemptState(
                    failed_attempts=2,
                    last_failed_at="2024-01-01 00:00:02.000",
                    last_error_message="RuntimeError: boom",
                    resolved=False,
                )
            },
            event_id="result-1",
            expected_status=SensorTickStatus.SUCCEEDED,
            expected_tick_statuses=("started", "succeeded"),
            expected_tick_attempts=(3, 3),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dead_letter_when_retrying_then_event_is_rebuilt_and_re_evaluated(
    test_case: DeadLetterActionTestCase,
) -> None:
    repository: FakeSensorStateRepository = FakeSensorStateRepository(
        node_results=test_case.node_results,
        attempt_states=test_case.attempt_states,
    )
    dispatcher: SensorDispatcher = SensorDispatcher(repository=repository)
    registry: SensorRegistry = SensorRegistry(sensors={test_case.sensor.name: test_case.sensor})

    status: SensorTickStatus = dispatcher.retry_dead_letter(
        registry=registry,
        sensor_name=test_case.sensor.name,
        event_id=test_case.event_id,
        target="prod",
    )

    assert status is test_case.expected_status
    assert tuple(tick.status for tick in repository.recorded_ticks) == (
        test_case.expected_tick_statuses
    )
    assert tuple(tick.attempt for tick in repository.recorded_ticks) == (
        test_case.expected_tick_attempts
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DeadLetterActionTestCase(
            description="skipping a dead letter records the reason and resolves it",
            sensor=build_loaded_sensor(declaration=failing_sensor),
            node_results=(build_node_result_observation(),),
            attempt_states={
                ("failing_sensor", "result-1"): TickAttemptState(
                    failed_attempts=2,
                    last_failed_at="2024-01-01 00:00:02.000",
                    last_error_message="RuntimeError: boom",
                    resolved=False,
                )
            },
            event_id="result-1",
            expected_status=SensorTickStatus.SKIPPED,
            expected_tick_statuses=("skipped",),
            expected_tick_attempts=(2,),
            expected_skip_reason="acknowledged manually",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dead_letter_when_skipping_then_a_skipped_tick_resolves_it(
    test_case: DeadLetterActionTestCase,
) -> None:
    repository: FakeSensorStateRepository = FakeSensorStateRepository(
        node_results=test_case.node_results,
        attempt_states=test_case.attempt_states,
    )
    dispatcher: SensorDispatcher = SensorDispatcher(repository=repository)
    registry: SensorRegistry = SensorRegistry(sensors={test_case.sensor.name: test_case.sensor})

    dispatcher.skip_dead_letter(
        registry=registry,
        sensor_name=test_case.sensor.name,
        event_id=test_case.event_id,
        reason="acknowledged manually",
    )

    assert tuple(tick.status for tick in repository.recorded_ticks) == (
        test_case.expected_tick_statuses
    )
    assert tuple(tick.attempt for tick in repository.recorded_ticks) == (
        test_case.expected_tick_attempts
    )
    assert repository.recorded_ticks[0].skip_reason == test_case.expected_skip_reason
