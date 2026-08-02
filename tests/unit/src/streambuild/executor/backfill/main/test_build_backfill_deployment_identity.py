import pytest

from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.backfill.main.build_backfill_deployment_identity import (
    build_backfill_deployment_identity,
)
from tests.unit.src.streambuild.executor.backfill.main._test_types import (
    DeploymentIdentityTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeploymentIdentityTestCase(
            description="rejects an identity that cannot be recognized after publication",
            deployment_id="release_2026_07",
            expected_error_fragment=(
                "Deployment ID must match YYYYMMDDTHHMMSSZ_<alphanumeric-suffix>"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unrecognized_deployment_id_when_building_identity_then_it_is_rejected(
    test_case: DeploymentIdentityTestCase,
) -> None:
    with pytest.raises(BackfillExecutionError, match=test_case.expected_error_fragment):
        build_backfill_deployment_identity(deployment_id=test_case.deployment_id)
