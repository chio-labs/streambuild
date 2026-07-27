from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.adapter_ownership import (
    adapter_package_ownership,
    warehouse_driver_ownership,
)
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="compiler importing an adapter implementation faults",
            path="src/streambuild/compiler/planner/main/plan_deployment.py",
            source=dedent(
                """
                from streambuild.adapters.clickhouse.types import RawClickHouseClient
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="compiler importing the neutral adapter contract passes",
            path="src/streambuild/compiler/planner/main/plan_deployment.py",
            source=dedent(
                """
                from streambuild.adapter.classes.adapter_connection import AdapterConnection
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="executor importing an adapter implementation passes",
            path="src/streambuild/executor/backfill/main/execute_backfill.py",
            source=dedent(
                """
                from streambuild.adapters.clickhouse.types import RawClickHouseClient
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="runtime importing the retired top-level package faults",
            path="src/streambuild/executor/backfill/_helpers/replay.py",
            source=dedent(
                """
                from streambuild.clickhouse.render.main.render_resources import render_resources
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="runtime importing the retired integration package faults",
            path="src/streambuild/cli/entry/main/main.py",
            source=dedent(
                """
                from streambuild.integrations.clickhouse.client import ClickHouseClient
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="parent package import of retired ClickHouse package faults",
            path="src/streambuild/executor/backfill/_helpers/replay.py",
            source=dedent(
                """
                from streambuild import clickhouse
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="parent package import of retired integration package faults",
            path="src/streambuild/cli/entry/main/main.py",
            source=dedent(
                """
                from streambuild.integrations import clickhouse
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="dynamic import of retired ClickHouse package faults",
            path="src/streambuild/executor/backfill/_helpers/replay.py",
            source=dedent(
                """
                import importlib

                importlib.import_module("streambuild.clickhouse.rendering")
                """
            ),
            expected_fault_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_adapter_package_ownership_then_it_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=adapter_package_ownership,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="cli importing driver exceptions faults",
            path="src/streambuild/cli/entry/main/main.py",
            source=dedent(
                """
                from clickhouse_connect.driver.exceptions import DatabaseError
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="plain driver import outside the adapter faults",
            path="src/streambuild/executor/backfill/_helpers/replay.py",
            source=dedent(
                """
                import clickhouse_connect
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="clickhouse adapter importing the driver passes",
            path="src/streambuild/adapters/clickhouse/classes/clickhouse_connection.py",
            source=dedent(
                """
                import clickhouse_connect
                from clickhouse_connect.driver.exceptions import DatabaseError
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="neutral adapter contract without driver imports passes",
            path="src/streambuild/adapter/classes/adapter_connection.py",
            source=dedent(
                """
                from abc import ABC
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="dynamic driver import outside the adapter faults",
            path="src/streambuild/adapter/classes/adapter_connection.py",
            source=dedent(
                """
                __import__("clickhouse_connect.driver.client")
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="dynamic driver import inside the adapter passes",
            path="src/streambuild/adapters/clickhouse/classes/clickhouse_connection.py",
            source=dedent(
                """
                __import__("clickhouse_connect.driver.client")
                """
            ),
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_driver_ownership_then_it_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=warehouse_driver_ownership,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count
