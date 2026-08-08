import pytest

from streambuild.cli.build._helpers.confirmation import confirm_build
from tests.unit.src.streambuild.cli.build._helpers._test_types import BuildConfirmationTestCase
from tests.unit.src.streambuild.cli.build._helpers.helpers import (
    build_confirmation_options,
    build_protection_requirement,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildConfirmationTestCase(
            description="unprotected auto-approved build proceeds",
            protection_requirements=(),
            auto_approve=True,
            confirmations=(),
            input_response=None,
            expected_confirmed=True,
            expected_stderr_fragment="",
        ),
        BuildConfirmationTestCase(
            description="protected auto-approved build rejects a missing word",
            protection_requirements=build_protection_requirement(),
            auto_approve=True,
            confirmations=(),
            input_response=None,
            expected_confirmed=False,
            expected_stderr_fragment="PROTECTED PIPELINE: protected_prices",
        ),
        BuildConfirmationTestCase(
            description="protected auto-approved build accepts the exact word",
            protection_requirements=build_protection_requirement(),
            auto_approve=True,
            confirmations=("DEPLOY_PROTECTED_PRICES",),
            input_response=None,
            expected_confirmed=True,
            expected_stderr_fragment="Interrupts protected trading prices.",
        ),
        BuildConfirmationTestCase(
            description="interactive protected build accepts a typed exact word",
            protection_requirements=build_protection_requirement(),
            auto_approve=False,
            confirmations=(),
            input_response="DEPLOY_PROTECTED_PRICES",
            expected_confirmed=True,
            expected_stderr_fragment="Interrupts protected trading prices.",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_build_protection_when_confirming_then_applies_required_gate(
    test_case: BuildConfirmationTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: test_case.input_response or "")

    confirmed: bool = confirm_build(
        options=build_confirmation_options(
            auto_approve=test_case.auto_approve,
            confirmations=test_case.confirmations,
        ),
        plan_text="plan",
        protection_requirements=test_case.protection_requirements,
    )

    assert confirmed is test_case.expected_confirmed
    assert test_case.expected_stderr_fragment in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
