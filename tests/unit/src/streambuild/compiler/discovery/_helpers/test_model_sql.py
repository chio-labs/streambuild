from pathlib import Path

import pytest

from streambuild.compiler.discovery._helpers.model_sql import (
    infer_transform_source,
    load_transform_from_sql_file,
    parse_model_sql,
)
from streambuild.spec.models.steps import TransformStep
from tests.unit.src.streambuild.compiler.discovery._helpers._test_types import (
    InferTransformSourceErrorTestCase,
    LoadTransformFromSqlFileTestCase,
    ParseModelSqlHeaderTestCase,
)
from tests.unit.src.streambuild.compiler.discovery.macros.helpers import (
    write_macro_file,
    write_project_file,
    write_sql_file,
)

TEST_CASES: list[ParseModelSqlHeaderTestCase] = [
    ParseModelSqlHeaderTestCase(
        description="accepts an empty model header",
        contents="""
        MODEL ();

        SELECT kafka_key::String AS order_id FROM __source("orders")
        """,
        expected_header_values={},
        expected_query='SELECT kafka_key::String AS order_id FROM __source("orders")',
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts blank lines inside multiline schema change backfill header",
        contents="""
        MODEL (
          engine: "MergeTree()",

          order_by: ["order_id"],
          replay_anchor: never,

          schema_change_backfill:
            breaking: bounded(8s)

            non_breaking: bounded(8s),
        );

        SELECT kafka_key::String AS order_id FROM __source("orders")
        """,
        expected_header_values={
            "engine": "MergeTree()",
            "order_by": ["order_id"],
            "replay_anchor": "never",
            "schema_change_backfill": {
                "breaking": "bounded(8s)",
                "non_breaking": "bounded(8s)",
            },
        },
        expected_query='SELECT kafka_key::String AS order_id FROM __source("orders")',
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts mixed block and inline header mappings",
        contents="""
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
          settings:
            index_granularity: 8192
            allow_nullable_key: 1,
          schema_change_backfill: {breaking: full, non_breaking: bounded(30m)},
        );

        SELECT kafka_key::String AS order_id FROM __source("orders")
        """,
        expected_header_values={
            "engine": "MergeTree()",
            "order_by": ["order_id"],
            "settings": {
                "index_granularity": 8192,
                "allow_nullable_key": 1,
            },
            "schema_change_backfill": {
                "breaking": "full",
                "non_breaking": "bounded(30m)",
            },
        },
        expected_query='SELECT kafka_key::String AS order_id FROM __source("orders")',
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts whitespace-only lines and indented header entries",
        contents=(
            "   \n"
            'MODEL (\n    engine: "MergeTree()",\n  \n'
            '    order_by: ["order_id"],\n'
            "    bounded_replay_fallback: bounded_without_history,\n"
            ");\n \n"
            'SELECT kafka_key::String AS order_id FROM __source("orders")'
        ),
        expected_header_values={
            "engine": "MergeTree()",
            "order_by": ["order_id"],
            "bounded_replay_fallback": "bounded_without_history",
        },
        expected_query='SELECT kafka_key::String AS order_id FROM __source("orders")',
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_sql_model_header_variants_when_parsing_then_it_returns_expected_header_values(
    test_case: ParseModelSqlHeaderTestCase,
) -> None:
    header_values, query = parse_model_sql(
        contents=test_case.contents, file_path=Path("orders.sql")
    )

    assert header_values == test_case.expected_header_values
    assert query == test_case.expected_query


@pytest.mark.parametrize(
    "test_case",
    [
        InferTransformSourceErrorTestCase(
            description="raises a specific error when the driving ref declares ref_type",
            query='SELECT order_id FROM __ref("orders", ref_type="reference")',
            expected_error_fragment="must not declare ref_type for its driving input 'orders'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_driving_ref_when_inferring_transform_source_then_it_raises_specific_error(
    test_case: InferTransformSourceErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        infer_transform_source(query=test_case.query, file_path=Path("orders.sql"))


@pytest.mark.parametrize(
    "test_case",
    [
        LoadTransformFromSqlFileTestCase(
            description="expands project macros in the sql model body only",
            macro_file_contents="""
            def replay_columns() -> str:
                return "_replay_partition AS _replay_partition"
            """,
            model_file_contents="""
            MODEL (
              order_by: ["order_id"]
            );

            SELECT order_id, @replay_columns() FROM __source("orders")
            """,
            expected_query_fragment=(
                'SELECT order_id, _replay_partition AS _replay_partition FROM __source("orders")'
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_model_macros_when_loading_then_it_expands_query_body(
    test_case: LoadTransformFromSqlFileTestCase,
    tmp_path: Path,
) -> None:
    write_project_file(tmp_path)
    write_macro_file(tmp_path, "common_columns.py", test_case.macro_file_contents)
    model_file_path: Path = write_sql_file(
        tmp_path,
        "pipelines/orders/order_items.sql",
        test_case.model_file_contents,
    )

    transform: TransformStep = load_transform_from_sql_file(model_file_path)

    assert transform.query is not None
    assert test_case.expected_query_fragment in transform.query
