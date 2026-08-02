from textwrap import dedent

import pytest
from fensu import RuleCase, RuleFile, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.workflow_authority import (
    published_workflow_capability,
    workflow_consumer_purity,
    workflow_mutation_gateway,
    workflow_statement_ownership,
)
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase

_CLICKHOUSE_CONNECTION_FILE: RuleFile = RuleFile(
    path=("src/streambuild/adapters/clickhouse/classes/clickhouse_connection.py"),
    source=dedent(
        """
        from streambuild.adapter.classes.adapter_connection import (
            AdapterConnection as BaseConnection,
        )

        class ClickHouseConnection(BaseConnection):
            pass
        """
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="allows the exact gateway to call the adapter method",
            path="src/streambuild/executor/workflow/main/_execute_warehouse_workflow.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection

                def execute(connection: AdapterConnection) -> None:
                    connection.execute_workflow_sql("SELECT 1;")
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects a direct imported adapter receiver",
            path="src/streambuild/executor/direct/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection

                def execute(connection: AdapterConnection) -> None:
                    connection.execute_workflow_sql("DROP TABLE events;")
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects an aliased adapter type and bound method alias",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import (
                    AdapterConnection as Connection,
                )

                def execute(connection: Connection) -> None:
                    adapter = connection
                    run_sql = adapter.execute_workflow_sql
                    run_sql("DROP TABLE events;")
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects a class-level adapter method call through an import alias",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import (
                    AdapterConnection as Connection,
                )

                def execute(connection: Connection) -> None:
                    Connection.execute_workflow_sql(connection, "DROP TABLE events;")
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects a proven concrete ClickHouse receiver without adapter import",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.adapters.clickhouse.classes.clickhouse_connection import (
                    ClickHouseConnection as Warehouse,
                )

                def execute(connection: Warehouse) -> None:
                    connection.execute_workflow_sql("DROP TABLE events;")
                """
            ),
            expected_fault_count=1,
            expected_dependency_count=1,
            files=(_CLICKHOUSE_CONNECTION_FILE,),
        ),
        CustomRuleTestCase(
            description="allows an unproven same-named ClickHouse class near the concrete boundary",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.adapters.clickhouse.classes.clickhouse_connection import (
                    ClickHouseConnection,
                )

                def execute(connection: ClickHouseConnection) -> None:
                    connection.execute_workflow_sql("metric")
                """
            ),
            expected_fault_count=0,
            expected_dependency_count=1,
            files=(
                RuleFile(
                    path=("src/streambuild/adapters/clickhouse/classes/clickhouse_connection.py"),
                    source="class ClickHouseConnection:\n    pass\n",
                ),
            ),
        ),
        CustomRuleTestCase(
            description="allows an unrelated same-named method despite adapter imports",
            path="src/streambuild/cli/build/_helpers/metrics.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection

                class Metrics:
                    def execute_workflow_sql(self, value: str) -> None:
                        pass

                def record(metrics: Metrics) -> None:
                    metrics.execute_workflow_sql("count")
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects the real call one filename outside the exact gateway",
            path="src/streambuild/executor/workflow/main/execute_warehouse_workflow.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection

                def execute(connection: AdapterConnection) -> None:
                    connection.execute_workflow_sql("DROP TABLE events;")
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="preserves retired mutation method enforcement on real receivers",
            path="src/streambuild/executor/direct/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection

                def execute(connection: AdapterConnection) -> None:
                    connection.insert_rows("events")
                """
            ),
            expected_fault_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_mutation_gateway_then_only_owner_may_call_it(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=workflow_mutation_gateway,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )
    repeated_result: RuleResult = evaluate_rule(
        rule=workflow_mutation_gateway,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result == repeated_result
    assert result.fault_count == test_case.expected_fault_count
    assert len(result.dependencies) == test_case.expected_dependency_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="allows publication owner to construct the imported capability",
            path="src/streambuild/cli/workflow_artifacts/main/_publish_build_workflow.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import PublishedBuildWorkflow

                published = PublishedBuildWorkflow(workflow, root, digest)
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="allows publication owner to construct an aliased real capability",
            path="src/streambuild/cli/workflow_artifacts/main/_publish_build_workflow.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import PublishedBuildWorkflow as Published

                published = Published(workflow, root, digest)
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects aliased real capability construction outside publication",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import PublishedBuildWorkflow as Published

                published = Published(workflow, root, digest)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects module-aliased real capability construction outside publication",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                import streambuild.executor.workflow.models as workflow_models

                published = workflow_models.PublishedBuildWorkflow(workflow, root, digest)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="allows an unrelated same-named capability class",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from metrics.models import PublishedBuildWorkflow

                published = PublishedBuildWorkflow(workflow, root, digest)
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects real capability construction just outside publication owner",
            path="src/streambuild/cli/workflow_artifacts/main/publish_build_workflow.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import PublishedBuildWorkflow

                published = PublishedBuildWorkflow(workflow, root, digest)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="allows exact execution parameters with aliased canonical types",
            path="src/streambuild/executor/workflow/main/execute_build_workflow.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import (
                    AdapterConnection as Connection,
                )
                from streambuild.executor.workflow.models import PublishedBuildWorkflow as Published

                def execute_build_workflow(
                    *, published_workflow: Published, connection: Connection
                ) -> None:
                    pass
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects execution accepting the raw build workflow",
            path="src/streambuild/executor/workflow/main/execute_build_workflow.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection
                from streambuild.executor.workflow.models import BuildWorkflow

                def execute_build_workflow(
                    *, workflow: BuildWorkflow, connection: AdapterConnection
                ) -> None:
                    pass
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects an unrelated same-named capability annotation",
            path="src/streambuild/executor/workflow/main/execute_build_workflow.py",
            source=dedent(
                """
                from metrics.models import PublishedBuildWorkflow
                from streambuild.adapter.classes.adapter_connection import AdapterConnection

                def execute_build_workflow(
                    *, published_workflow: PublishedBuildWorkflow, connection: AdapterConnection
                ) -> None:
                    pass
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects an extra execution parameter",
            path="src/streambuild/executor/workflow/main/execute_build_workflow.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection
                from streambuild.executor.workflow.models import PublishedBuildWorkflow

                def execute_build_workflow(
                    *, published_workflow: PublishedBuildWorkflow,
                    connection: AdapterConnection,
                    workflow: object,
                ) -> None:
                    pass
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects a wrong connection parameter type",
            path="src/streambuild/executor/workflow/main/execute_build_workflow.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import PublishedBuildWorkflow

                def execute_build_workflow(
                    *, published_workflow: PublishedBuildWorkflow, connection: object
                ) -> None:
                    pass
                """
            ),
            expected_fault_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_capability_then_only_publication_constructs_it(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=published_workflow_capability,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )
    repeated_result: RuleResult = evaluate_rule(
        rule=published_workflow_capability,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result == repeated_result
    assert result.fault_count == test_case.expected_fault_count
    assert len(result.dependencies) == test_case.expected_dependency_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="allows direct tuple iteration in execution",
            path="src/streambuild/executor/workflow/main/_execute_warehouse_workflow.py",
            source=dedent(
                """
                def execute(statements: tuple[object, ...]) -> None:
                    for statement in statements:
                        consume(statement.sql)
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects sorting in publication",
            path="src/streambuild/cli/workflow_artifacts/main/_publish_build_workflow.py",
            source="ordered = sorted(workflow.statements)\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects adapter rendering in execution",
            path="src/streambuild/executor/workflow/main/_execute_warehouse_workflow.py",
            source="sql = connection.render_resource(resource=value, database='analytics')\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects planning in publication",
            path="src/streambuild/cli/workflow_artifacts/main/_publish_build_workflow.py",
            source="plan = plan_deployment(desired_state)\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects statement construction in a consumer",
            path="src/streambuild/cli/workflow_artifacts/main/_publish_build_workflow.py",
            source="statement = WarehouseStatement(1, 'step', phase, intent, sql)\n",
            expected_fault_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_consumer_when_checking_purity_then_it_cannot_derive_workflow_decisions(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=workflow_consumer_purity,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )
    repeated_result: RuleResult = evaluate_rule(
        rule=workflow_consumer_purity,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result == repeated_result
    assert result.fault_count == test_case.expected_fault_count
    assert len(result.dependencies) == test_case.expected_dependency_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="allows direct assembler to construct the real statement",
            path="src/streambuild/executor/direct/_helpers/workflow.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import WarehouseStatement

                statement = WarehouseStatement(1, 'step', phase, intent, sql)
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="allows assembler to construct an aliased real statement",
            path="src/streambuild/executor/backfill/_helpers/workflow.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import WarehouseStatement as Statement

                statement = Statement(1, 'step', phase, intent, sql)
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects aliased real statement construction in cli",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import WarehouseStatement as Statement

                statement = Statement(1, 'step', phase, intent, sql)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="rejects module-aliased real statement construction in adapter",
            path="src/streambuild/adapters/clickhouse/_helpers/rendering.py",
            source=dedent(
                """
                import streambuild.executor.workflow.models as workflow_models

                statement = workflow_models.WarehouseStatement(1, 'step', phase, intent, sql)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="allows an unrelated same-named statement class",
            path="src/streambuild/cli/build/_helpers/execution.py",
            source=dedent(
                """
                from metrics.models import WarehouseStatement

                statement = WarehouseStatement(1, 'step', phase, intent, sql)
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="rejects real statement construction just outside assembler path",
            path="src/streambuild/executor/direct/_helpers/workflows.py",
            source=dedent(
                """
                from streambuild.executor.workflow.models import WarehouseStatement

                statement = WarehouseStatement(1, 'step', phase, intent, sql)
                """
            ),
            expected_fault_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_constructor_when_checking_statement_ownership_then_only_assemblers_pass(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=workflow_statement_ownership,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )
    repeated_result: RuleResult = evaluate_rule(
        rule=workflow_statement_ownership,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result == repeated_result
    assert result.fault_count == test_case.expected_fault_count
    assert len(result.dependencies) == test_case.expected_dependency_count
