from pathlib import Path

import pytest

from streambuild.compiler.discovery.shared.helpers.macros.main import expand_project_sql_macros
from tests.unit.src.streambuild.compiler.discovery.macros._test_types import (
    ExpandProjectSqlMacrosCollisionTestCase,
    ExpandProjectSqlMacrosErrorTestCase,
    ExpandProjectSqlMacrosTestCase,
)
from tests.unit.src.streambuild.compiler.discovery.macros.helpers import (
    write_macro_file,
    write_project_file,
    write_sql_file,
)

TEST_CASES: list[ExpandProjectSqlMacrosTestCase] = [
    ExpandProjectSqlMacrosTestCase(
        description="expands a simple sql macro from the project macros directory",
        macro_file_name="common_columns.py",
        macro_file_contents="""
        def replay_columns() -> str:
            return "_replay_partition AS _replay_partition"
        """,
        sql_body="SELECT @replay_columns() FROM source_table",
        expected_expanded_fragment=(
            "SELECT _replay_partition AS _replay_partition FROM source_table"
        ),
    ),
    ExpandProjectSqlMacrosTestCase(
        description="supports nested macro calls inside arguments",
        macro_file_name="mock_helpers.py",
        macro_file_contents="""
        def load_fixture(name: str) -> list[dict[str, object]]:
            if name != "orders":
                raise ValueError("unexpected fixture")
            return [
                {"order_id": "ord_001", "quantity": 2, "unit_price": 10.0},
                {"order_id": "ord_002", "quantity": None, "unit_price": 5.0},
            ]

        def mock_rows(rows: list[dict[str, object]]) -> str:
            selects: list[str] = []
            for row in rows:
                selects.append(
                    "SELECT "
                    + ", ".join(
                        "NULL AS {key}".format(key=key)
                        if value is None
                        else "'{value}' AS {key}".format(value=value, key=key)
                        if isinstance(value, str)
                        else "{value} AS {key}".format(value=value, key=key)
                        for key, value in row.items()
                    )
                )
            return " UNION ALL ".join(selects)
        """,
        sql_body='WITH __source__orders AS (@mock_rows(@load_fixture("orders"))) SELECT 1',
        expected_expanded_fragment=(
            "WITH __source__orders AS (SELECT 'ord_001' AS order_id, 2 AS quantity, "
            "10.0 AS unit_price "
            "UNION ALL SELECT 'ord_002' AS order_id, NULL AS quantity, 5.0 AS unit_price) SELECT 1"
        ),
    ),
    ExpandProjectSqlMacrosTestCase(
        description="supports nested macro arguments alongside literal positional arguments",
        macro_file_name="arg_helpers.py",
        macro_file_contents="""
        def load_fixture(name: str) -> list[dict[str, object]]:
            return [{"order_id": "ord_001"}, {"order_id": "ord_002"}] if name == "orders" else []

        def wrap_rows(rows: list[dict[str, object]], key_column: str) -> str:
            return "SELECT " + ", ".join(row[key_column] for row in rows)
        """,
        sql_body='SELECT @wrap_rows(@load_fixture("orders"), "order_id")',
        expected_expanded_fragment="SELECT SELECT ord_001, ord_002",
    ),
    ExpandProjectSqlMacrosTestCase(
        description="supports named macro arguments with nested values",
        macro_file_name="kwarg_helpers.py",
        macro_file_contents="""
        def load_fixture(name: str) -> list[dict[str, object]]:
            return [{"order_id": "ord_001"}] if name == "orders" else []

        def wrap_rows(*, rows: list[dict[str, object]], key_column: str) -> str:
            return "SELECT " + rows[0][key_column]
        """,
        sql_body='SELECT @wrap_rows(rows=@load_fixture("orders"), key_column="order_id")',
        expected_expanded_fragment="SELECT SELECT ord_001",
    ),
    ExpandProjectSqlMacrosTestCase(
        description="supports mixed positional and named macro arguments",
        macro_file_name="mixed_arg_helpers.py",
        macro_file_contents="""
        def load_fixture(name: str) -> list[dict[str, object]]:
            return [{"order_id": "ord_001"}, {"order_id": "ord_002"}] if name == "orders" else []

        def limit_rows(rows: list[dict[str, object]], *, limit: int) -> str:
            return "SELECT " + ", ".join(row["order_id"] for row in rows[:limit])
        """,
        sql_body='SELECT @limit_rows(@load_fixture("orders"), limit=1)',
        expected_expanded_fragment="SELECT SELECT ord_001",
    ),
    ExpandProjectSqlMacrosTestCase(
        description="supports multiple nested macros in one call",
        macro_file_name="multi_nested_helpers.py",
        macro_file_contents="""
        def left_rows() -> list[str]:
            return ["ord_001", "ord_002"]

        def right_rows() -> list[str]:
            return ["ord_003"]

        def join_rows(left: list[str], right: list[str], separator: str) -> str:
            return "SELECT " + separator.join([*left, *right])
        """,
        sql_body='SELECT @join_rows(@left_rows(), @right_rows(), ", ")',
        expected_expanded_fragment="SELECT SELECT ord_001, ord_002, ord_003",
    ),
]

ERROR_TEST_CASES: list[ExpandProjectSqlMacrosErrorTestCase] = [
    ExpandProjectSqlMacrosErrorTestCase(
        description="raises a clear error for unknown macros",
        macro_file_name="common_columns.py",
        macro_file_contents="""
        def replay_columns() -> str:
            return "order_id"
        """,
        sql_body="SELECT @unknown_macro()",
        expected_error_fragment="Unknown macro '@unknown_macro'",
    ),
    ExpandProjectSqlMacrosErrorTestCase(
        description="raises a clear error for meta macro output",
        macro_file_name="common_columns.py",
        macro_file_contents="""
        def outer_macro() -> str:
            return "@inner_macro()"

        def inner_macro() -> str:
            return "order_id"
        """,
        sql_body="SELECT @outer_macro()",
        expected_error_fragment=(
            r"produced output containing unexpanded macro call '@inner_macro\('"
        ),
    ),
    ExpandProjectSqlMacrosErrorTestCase(
        description="raises a clear error when a top level macro returns a non string",
        macro_file_name="bad_macro.py",
        macro_file_contents="""
        def bad_macro() -> list[str]:
            return ["ord_001"]
        """,
        sql_body="SELECT @bad_macro()",
        expected_error_fragment="must return a SQL string when used directly in SQL",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_project_macros_when_expanding_then_it_returns_expected_sql(
    test_case: ExpandProjectSqlMacrosTestCase,
    tmp_path: Path,
) -> None:
    write_project_file(tmp_path)
    write_macro_file(tmp_path, test_case.macro_file_name, test_case.macro_file_contents)
    sql_file_path: Path = write_sql_file(
        tmp_path, "pipelines/orders/order_items.sql", test_case.sql_body
    )

    expanded_sql: str = expand_project_sql_macros(sql=test_case.sql_body, file_path=sql_file_path)

    assert test_case.expected_expanded_fragment in expanded_sql


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_project_macros_when_expanding_then_it_raises_clear_errors(
    test_case: ExpandProjectSqlMacrosErrorTestCase,
    tmp_path: Path,
) -> None:
    write_project_file(tmp_path)
    write_macro_file(tmp_path, test_case.macro_file_name, test_case.macro_file_contents)
    sql_file_path: Path = write_sql_file(
        tmp_path, "pipelines/orders/order_items.sql", test_case.sql_body
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        expand_project_sql_macros(sql=test_case.sql_body, file_path=sql_file_path)


@pytest.mark.parametrize(
    "test_case",
    [
        ExpandProjectSqlMacrosCollisionTestCase(
            description="raises a clear error for colliding macro names",
            first_macro_file_name="common.py",
            first_macro_file_contents="""
            def replay_columns() -> str:
                return "order_id"
            """,
            second_macro_file_name="nested/other.py",
            second_macro_file_contents="""
            def replay_columns() -> str:
                return "customer_id"
            """,
            sql_body="SELECT @replay_columns()",
            expected_error_fragment="Macro name collision for 'replay_columns'",
        )
    ],
    ids=["raises a clear error for colliding macro names"],
)
def test_given_colliding_macro_names_when_expanding_then_it_raises_clear_error(
    test_case: ExpandProjectSqlMacrosCollisionTestCase,
    tmp_path: Path,
) -> None:
    write_project_file(tmp_path)
    write_macro_file(
        tmp_path,
        test_case.first_macro_file_name,
        test_case.first_macro_file_contents,
    )
    write_macro_file(
        tmp_path,
        test_case.second_macro_file_name,
        test_case.second_macro_file_contents,
    )
    sql_file_path: Path = write_sql_file(
        tmp_path,
        "pipelines/orders/order_items.sql",
        test_case.sql_body,
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        expand_project_sql_macros(sql=test_case.sql_body, file_path=sql_file_path)
