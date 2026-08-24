import pytest
from pydantic import ValidationError

from streambuild.dev_server.models import (
    DestructionExecutionRequest,
    DestructionPlanRequest,
)
from tests.unit.src.streambuild.dev_server._test_types import (
    DestructionChallengeWhitespaceTestCase,
    DestructionRequestValidationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionRequestValidationTestCase(
            description="confirmed bypass field is rejected from plan requests",
            field="confirmed",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="force bypass field is rejected from plan requests",
            field="force",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="yes bypass field is rejected from plan requests",
            field="yes",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="skip review bypass field is rejected from plan requests",
            field="skipReview",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="auto approve bypass field is rejected from plan requests",
            field="autoApprove",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_confirmation_bypass_field_when_validating_plan_then_request_is_rejected(
    test_case: DestructionRequestValidationTestCase,
) -> None:
    payload: dict[str, object] = {
        "operation": "destroy_pipelines",
        "pipelineNames": ["orders"],
        test_case.field: test_case.value,
    }

    with pytest.raises(ValidationError, match=test_case.expected_error_fragment):
        DestructionPlanRequest.model_validate(payload)


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionRequestValidationTestCase(
            description="confirmed bypass field is rejected from execution requests",
            field="confirmed",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="force bypass field is rejected from execution requests",
            field="force",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="yes bypass field is rejected from execution requests",
            field="yes",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="skip review bypass field is rejected from execution requests",
            field="skipReview",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="auto approve bypass field is rejected from execution requests",
            field="autoApprove",
            value=True,
            expected_error_fragment="Extra inputs are not permitted",
        ),
        DestructionRequestValidationTestCase(
            description="mutable pipeline names are rejected from execution requests",
            field="pipelineNames",
            value=["orders"],
            expected_error_fragment="Extra inputs are not permitted",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_bypass_or_mutable_plan_field_when_validating_execution_then_request_is_rejected(
    test_case: DestructionRequestValidationTestCase,
) -> None:
    payload: dict[str, object] = {
        "responses": ["orders"],
        test_case.field: test_case.value,
    }

    with pytest.raises(ValidationError, match=test_case.expected_error_fragment):
        DestructionExecutionRequest.model_validate(payload)


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionChallengeWhitespaceTestCase(
            description="challenge whitespace remains exact",
            responses=[" orders "],
            expected_responses=[" orders "],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_whitespace_when_validating_challenge_then_value_is_not_normalized(
    test_case: DestructionChallengeWhitespaceTestCase,
) -> None:
    request: DestructionExecutionRequest = DestructionExecutionRequest(
        responses=test_case.responses
    )

    assert request.responses == test_case.expected_responses


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
