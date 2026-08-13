from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.event_catalog_authority import event_catalog_authority
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="rejects event construction outside the events catalog",
            path="src/streambuild/sensors/classes/sensor_dispatcher.py",
            source=dedent(
                """
                from streambuild.events.models import AuditCompleted

                def emit() -> AuditCompleted:
                    return AuditCompleted(
                        id="one",
                        audit_name="orders_fresh",
                        status="failed",
                        transition="new_failure",
                        severity=None,
                        failure_count=1,
                        target="prod",
                        trigger="scheduled",
                        completed_at="2024-01-01 00:00:00.000",
                        binding_key="key",
                        invocation_id="inv",
                        scheduled_for=None,
                        error_message=None,
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects run event construction in the dev server",
            path="src/streambuild/dev_server/_helpers/server/api_routes.py",
            source=dedent(
                """
                from streambuild.events.models import RunCompleted

                def emit() -> RunCompleted:
                    return RunCompleted(
                        id="one",
                        command="build",
                        mode=None,
                        outcome="succeeded",
                        exit_code=0,
                        target="prod",
                        deployment_id=None,
                        selected_node_count=1,
                        error_message=None,
                        completed_at="2024-01-01 00:00:00.000",
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="allows event construction inside the events catalog",
            path="src/streambuild/events/main/events_from_node_result.py",
            source=dedent(
                """
                from streambuild.events.models import AuditCompleted

                def derive() -> str:
                    return "AuditCompleted(" + ")"
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="allows consuming events without constructing them",
            path="src/streambuild/sensors/_helpers/dispatch.py",
            source=dedent(
                """
                from streambuild.events.models import AuditCompleted

                def matches(event: AuditCompleted) -> bool:
                    return event.target == "prod"
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="ignores modules outside the product scope",
            path="scripts/fensu_policy/constants.py",
            source='EVENT = "AuditCompleted("\n',
            expected_fault_count=0,
            scope="tooling",
            scope_root=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_source_when_checking_event_catalog_authority_then_faults_match(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=event_catalog_authority,
        test_case=RuleCase(
            description=test_case.description,
            path=test_case.path,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count
