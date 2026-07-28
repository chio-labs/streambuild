import pytest

from streambuild.adapter.models import AdapterQueryResult
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import StandardPopulationSegment
from streambuild.executor.standard._helpers.boundaries import (
    capture_population_segment_boundaries,
)
from streambuild.executor.standard.models import StandardReplayBoundary
from tests.unit.src.streambuild.executor.standard._helpers._test_types import (
    ScalarBoundaryTestCase,
)
from tests.unit.src.streambuild.executor.standard._helpers.helpers import (
    ScalarBoundaryRecordingConnection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ScalarBoundaryTestCase(
            description="empty target uses the preserved input maximum despite clock skew",
            source_maximum="2099-01-01 00:00:00.000",
            expected_query_statements=(
                "SELECT max(_replay_timestamp) FROM analytics.tbl__alpha HAVING count() > 0",
                "SELECT min(_replay_timestamp) FROM analytics.tbl__beta HAVING count() > 0",
            ),
            expected_cutoff_value="2099-01-01 00:00:00.000",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scalar_source_when_capturing_empty_target_then_source_maximum_is_inclusive(
    test_case: ScalarBoundaryTestCase,
) -> None:
    connection: ScalarBoundaryRecordingConnection = ScalarBoundaryRecordingConnection(
        query_results=(
            AdapterQueryResult(rows=((test_case.source_maximum,),)),
            AdapterQueryResult(rows=()),
        )
    )
    segment: StandardPopulationSegment = StandardPopulationSegment(
        model_key=LogicalResourceKey(resource_type=LogicalResourceType.MODEL, name="beta"),
        driving_input_key=LogicalResourceKey(resource_type=LogicalResourceType.MODEL, name="alpha"),
        driving_input_relation_name="tbl__alpha",
        replay_boundary_mode=ReplayLineageMode.TIMESTAMP,
    )

    boundaries: tuple[StandardReplayBoundary, ...] = capture_population_segment_boundaries(
        client=connection,
        segment=segment,
        database="analytics",
        target_relation_name="tbl__beta",
    )

    assert tuple(connection.query_statements) == test_case.expected_query_statements
    assert len(boundaries) == 1
    assert boundaries[0].cutoff_value == test_case.expected_cutoff_value
    assert boundaries[0].cutoff_inclusive is True
