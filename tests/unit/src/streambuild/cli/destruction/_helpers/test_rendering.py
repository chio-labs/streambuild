import builtins
from unittest.mock import MagicMock

import pytest

from streambuild.cli.destruction._helpers.rendering import (
    read_destruction_challenges,
    render_destruction_plan,
)
from streambuild.executor.destruction.models import DestructionPlan
from tests.unit.src.streambuild.cli.destruction._helpers._test_types import (
    DestructionChallengeInputTestCase,
    DestructionRenderingTestCase,
)
from tests.unit.src.streambuild.cli.destruction.helpers import destruction_plan


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionRenderingTestCase(
            description="renders frozen scope evidence relations preservation and challenges",
            expected_fragments=(
                "Plan ID: destruction_reviewed",
                "Operation: destroy_pipelines",
                "Target: uat",
                "Database: analytics",
                "Created at: 2026-08-24T12:00:00+00:00",
                "Manifest fingerprint: manifest-sha",
                "Plan fingerprint: plan-sha",
                "Requested pipelines: alpha",
                "Affected models: orders",
                "Preserves managed sources: yes",
                "Estimated active-part bytes: 2048",
                "Irreversible: yes",
                "Recreation: authored definitions remain",
                "- analytics.tbl__orders",
                "  Kind: table",
                "  Active parts: 2",
                "  Catalog fingerprint: catalog-sha",
                "  Ownership: current_manifest",
                "  Dependencies: none",
                "Required typed challenges:\n- alpha",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_frozen_plan_when_rendering_then_complete_evidence_is_printed(
    test_case: DestructionRenderingTestCase,
) -> None:
    # Given: A frozen plan containing warehouse evidence.
    plan: DestructionPlan = destruction_plan()

    # When: The operator-facing plan is rendered.
    rendered: str = render_destruction_plan(plan)

    # Then: Every safety-relevant section is present before review.
    for fragment in test_case.expected_fragments:
        assert fragment in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionChallengeInputTestCase(
            description="preserves surrounding challenge whitespace",
            response=" alpha ",
            expected_responses=(" alpha ",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_challenge_when_reading_then_response_is_not_stripped(
    test_case: DestructionChallengeInputTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Input containing whitespace around the challenge.
    input_mock: MagicMock = MagicMock(return_value=test_case.response)
    monkeypatch.setattr(builtins, "input", input_mock)

    # When: The challenge is read.
    responses: tuple[str, ...] = read_destruction_challenges(destruction_plan())

    # Then: The exact entered value is retained for store validation.
    assert responses == test_case.expected_responses
