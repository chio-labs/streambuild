from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.observability_authority import observability_non_authority
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="rejects planner use of the Quality history renderer",
            path="src/streambuild/compiler/planner/main/load_actual_state.py",
            source=dedent(
                """
                def load(connection) -> str:
                    return connection.render_latest_node_status_query(
                        database="metadata",
                        project_identity="project",
                        target_identity="analytics",
                        nodes=(),
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects planner aliases of the Quality history renderer",
            path="src/streambuild/compiler/planner/_helpers/load_actual_state.py",
            source=dedent(
                """
                def load(connection) -> str:
                    renderer = connection.render_latest_node_status_query
                    return renderer(
                        database="metadata",
                        project_identity="project",
                        target_identity="analytics",
                        nodes=(),
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects aliased observability table constant imports in janitor",
            path="src/streambuild/executor/janitor/_helpers/execute.py",
            source=dedent(
                """
                from streambuild.adapter.constants import (
                    METADATA_INVOCATIONS_TABLE_NAME as HISTORY_TABLE,
                )

                def read() -> str:
                    return HISTORY_TABLE
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects raw observability table names in publish decisions",
            path="src/streambuild/executor/publish/_helpers/resolution.py",
            source='QUERY = "SELECT * FROM _streambuild_node_results"\n',
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects module-qualified observability constants in repair",
            path="src/streambuild/cli/repair_active_view/main/_run_repair_active_view.py",
            source=dedent(
                """
                import streambuild.adapter.constants as adapter_constants

                def read() -> str:
                    return adapter_constants.METADATA_NODE_RESULTS_TABLE_NAME
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects Quality history reads from build workflow execution",
            path="src/streambuild/executor/workflow/main/execute_build_workflow.py",
            source=dedent(
                """
                def execute(connection) -> str:
                    return connection.render_latest_node_status_query(
                        database="metadata",
                        project_identity="project",
                        target_identity="analytics",
                        nodes=(),
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects Quality history reads from the mutation gateway",
            path=("src/streambuild/executor/workflow/main/_execute_warehouse_workflow.py"),
            source='QUERY = "SELECT * FROM _streambuild_invocations"\n',
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects Quality history reads from CLI dispatch",
            path="src/streambuild/cli/entry/_helpers/dispatch.py",
            source=dedent(
                """
                def dispatch(connection) -> str:
                    renderer = connection.render_latest_node_status_query
                    return renderer(
                        database="metadata",
                        project_identity="project",
                        target_identity="analytics",
                        nodes=(),
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects Quality history reads from shared CLI selection",
            path="src/streambuild/cli/selection/main/_selection.py",
            source='QUERY = "SELECT * FROM _streambuild_node_results"\n',
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects planner imports of UI history readers",
            path="src/streambuild/compiler/planner/_helpers/load_actual_state.py",
            source=dedent(
                """
                from streambuild.quality.main.read_history import read_history

                def load() -> object:
                    return read_history()
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects split from-imports of the Quality domain",
            path="src/streambuild/executor/reconcile/_helpers/preview.py",
            source=dedent(
                """
                from streambuild import quality

                def load() -> object:
                    return quality.read_history()
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects dynamic imports of UI history readers",
            path="src/streambuild/cli/build/_helpers/preview.py",
            source=dedent(
                """
                import importlib

                def load() -> object:
                    return importlib.import_module(
                        "streambuild.quality.main.read_history"
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects imported dynamic loaders of UI history readers",
            path="src/streambuild/cli/build/_helpers/preview.py",
            source=dedent(
                """
                from importlib import import_module

                def load() -> object:
                    return import_module("streambuild.quality.main.read_history")
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects module-aliased dynamic loaders of UI history readers",
            path="src/streambuild/cli/plan/_helpers/plan_rendering.py",
            source=dedent(
                """
                import importlib as loader

                def load() -> object:
                    return loader.import_module(
                        "streambuild.quality.main.read_history"
                    )
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="allows the ClickHouse adapter to render Quality history",
            path="src/streambuild/adapters/clickhouse/_helpers/metadata.py",
            source=dedent(
                """
                def render() -> str:
                    return "SELECT * FROM _streambuild_node_results"
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="allows observability persistence to name its own tables",
            path="src/streambuild/executor/observability/_helpers/workflow.py",
            source=dedent(
                """
                from streambuild.adapter.constants import METADATA_INVOCATIONS_TABLE_NAME

                def render() -> str:
                    return METADATA_INVOCATIONS_TABLE_NAME
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="allows observation workflow persistence to name history tables",
            path=("src/streambuild/executor/workflow/main/_execute_observation_workflow.py"),
            source='QUERY = "INSERT INTO _streambuild_node_results"\n',
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="allows a UI consumer to read Quality history",
            path="src/streambuild/quality/main/read_history.py",
            source='QUERY = "SELECT * FROM _streambuild_invocations"\n',
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_observability_authority_then_only_ui_paths_may_read(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=observability_non_authority,
        test_case=RuleCase(
            description=test_case.description,
            path=test_case.path,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
        ),
    )
    repeated_result: RuleResult = evaluate_rule(
        rule=observability_non_authority,
        test_case=RuleCase(
            description=test_case.description,
            path=test_case.path,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
        ),
    )

    assert result == repeated_result
    assert result.fault_count == test_case.expected_fault_count
