"""Behavior tests for the provider base, session lifecycle, and injection."""

import pytest

from streambuild.provider.classes.session import ProviderSession
from streambuild.provider.exceptions import (
    ProviderInjectionError,
    ProviderInputError,
    ProviderTeardownError,
)
from streambuild.provider.main.invoke_with_providers import invoke_with_providers
from tests.unit.src.streambuild.provider._test_types import (
    ProviderInjectionTestCase,
    ProviderNameErrorTestCase,
    ProviderNameTestCase,
    ProviderSessionTestCase,
    ProviderTeardownTestCase,
)
from tests.unit.src.streambuild.provider.helpers import (
    BadName,
    ExplodingTeardown,
    OpsSlack,
    QualitySlack,
    SlackRecorder,
    drain_lifecycle_log,
    handler_requiring_ops_slack,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderNameTestCase(
            description="camel case class names become snake case provider names",
            expected_name="quality_slack",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_class_when_resolving_name_then_snake_case_is_derived(
    test_case: ProviderNameTestCase,
) -> None:
    assert QualitySlack.name() == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderNameErrorTestCase(
            description="explicit provider names must be snake case identifiers",
            expected_error_fragment="invalid provider name",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_provider_name_when_resolving_then_input_error_is_raised(
    test_case: ProviderNameErrorTestCase,
) -> None:
    with pytest.raises(ProviderInputError, match=test_case.expected_error_fragment):
        _ = BadName.name()


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderSessionTestCase(
            description="providers set up lazily and tear down in reverse order",
            expected_lifecycle_log=(
                "setup:quality_slack",
                "setup:ops_slack",
                "teardown:ops_slack",
                "teardown:quality_slack",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_session_when_accessing_providers_then_lifecycle_is_lazy_and_lifo(
    test_case: ProviderSessionTestCase,
) -> None:
    _ = drain_lifecycle_log()
    session: ProviderSession = ProviderSession(
        {"quality_slack": QualitySlack(), "ops_slack": OpsSlack()}, setup_context=None
    )

    with session:
        _ = session.providers.quality_slack
        _ = session.providers.ops_slack

    assert drain_lifecycle_log() == test_case.expected_lifecycle_log


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderTeardownTestCase(
            description="teardown failures surface when the handler succeeded",
            expected_error_fragment="socket already closed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_teardown_failure_when_closing_then_error_surfaces(
    test_case: ProviderTeardownTestCase,
) -> None:
    session: ProviderSession = ProviderSession({"exploding_teardown": ExplodingTeardown()})
    _ = session.providers.exploding_teardown

    with pytest.raises(ProviderTeardownError, match=test_case.expected_error_fragment):
        session.close()


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderTeardownTestCase(
            description="teardown errors never mask the handler error",
            expected_error_fragment="socket already closed",
            expected_handler_error_fragment="handler exploded",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_handler_error_when_session_exits_then_teardown_error_never_masks_it(
    test_case: ProviderTeardownTestCase,
) -> None:
    session: ProviderSession = ProviderSession({"exploding_teardown": ExplodingTeardown()})

    with pytest.raises(RuntimeError, match=test_case.expected_handler_error_fragment):
        with session:
            _ = session.providers.exploding_teardown
            raise RuntimeError("handler exploded")

    assert isinstance(session.teardown_error, ProviderTeardownError)
    assert test_case.expected_error_fragment in str(session.teardown_error)


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderInjectionTestCase(
            description="annotated parameters receive providers by name",
            expected_injected_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_annotated_parameter_when_invoking_then_provider_is_injected_by_name(
    test_case: ProviderInjectionTestCase,
) -> None:
    session: ProviderSession = ProviderSession({"quality_slack": QualitySlack()})
    recorder: SlackRecorder = SlackRecorder()

    with session:
        _ = invoke_with_providers(
            function=recorder, context="the-context", providers=session.providers
        )

    assert len(recorder.seen) == test_case.expected_injected_count
    assert isinstance(recorder.seen[0], QualitySlack)


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderInjectionTestCase(
            description="annotated providers missing from the container fail loudly",
            expected_error_fragment="requires provider 'ops_slack', but it was not found",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_provider_when_invoking_then_injection_error_is_raised(
    test_case: ProviderInjectionTestCase,
) -> None:
    session: ProviderSession = ProviderSession({"quality_slack": QualitySlack()})

    with session:
        with pytest.raises(ProviderInjectionError, match=test_case.expected_error_fragment or ""):
            _ = invoke_with_providers(
                function=handler_requiring_ops_slack,
                context="the-context",
                providers=session.providers,
            )
