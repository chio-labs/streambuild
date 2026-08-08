from pathlib import Path

from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.test_discovery.models import (
    LoadedSqlTest,
    SqlTestCte,
    SqlTestModelPayload,
)
from streambuild.compiler.test_discovery.types import SqlTestMode
from streambuild.compiler.testing.models import SqlTestCase, SqlTestChainStep


def audit(*, path: Path, name: str, query: str, severity: str) -> LoadedSqlAudit:
    return LoadedSqlAudit(
        file_path=path,
        name=name,
        query=query,
        referenced_model_names=("orders",),
        severity=severity,
    )


def loaded_test() -> LoadedSqlTest:
    expected: SqlTestCte = SqlTestCte(name="__expected__orders", query="SELECT 1 AS order_id")
    return LoadedSqlTest(
        file_path=Path("/project/tests/orders.sql"),
        mode=SqlTestMode.MODEL,
        authored_ctes=(expected,),
        payload=SqlTestModelPayload(
            mocks=(),
            expected_targets=(expected,),
            assertions=(),
            assertion_reference_names=(),
        ),
        name="orders return ids",
    )


def build_test_case(model_query: str) -> SqlTestCase:
    return SqlTestCase(
        file_path=Path("/project/tests/orders.sql"),
        query=(f"WITH model_orders AS ({model_query}) SELECT * FROM model_orders"),
        target_cases=(
            SqlTestChainStep(
                target_model_name="orders",
                expected_column_names=("order_id",),
                ctes=(("model_orders", model_query),),
                actual_query="SELECT order_id FROM model_orders",
                expected_query="SELECT 1 AS order_id",
            ),
        ),
        name="orders return ids",
    )
