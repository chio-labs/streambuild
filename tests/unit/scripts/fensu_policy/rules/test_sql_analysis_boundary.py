from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.sql_analysis_boundary import sql_analysis_import_ownership
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="runtime outside SQL analysis importing Polyglot faults",
            path="src/streambuild/compiler/compile/_helpers/transforms.py",
            source="import polyglot_sql\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="SQL analysis importing Polyglot passes",
            path="src/streambuild/compiler/sql_analysis/_helpers/polyglot.py",
            source="import polyglot_sql\n",
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="SQL analysis importing removed engine faults",
            path="src/streambuild/compiler/sql_analysis/_helpers/polyglot.py",
            source="from sqlglot import parse_one\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="runtime importing removed engine faults",
            path="src/streambuild/compiler/compile/_helpers/sql_contract.py",
            source="from sqlglot import parse_one\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="dynamic Polyglot import outside boundary faults",
            path="src/streambuild/compiler/compile/_helpers/transforms.py",
            source=dedent(
                """
                import importlib

                importlib.import_module("polyglot_sql")
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="dynamic removed engine import inside boundary faults",
            path="src/streambuild/compiler/sql_analysis/_helpers/polyglot.py",
            source='__import__("sqlglot.expressions")\n',
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="dynamic removed engine import outside boundary faults",
            path="src/streambuild/compiler/compile/_helpers/transforms.py",
            source='importlib.import_module("sqlglot")\n',
            expected_fault_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_sql_analysis_ownership_then_it_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=sql_analysis_import_ownership,
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
