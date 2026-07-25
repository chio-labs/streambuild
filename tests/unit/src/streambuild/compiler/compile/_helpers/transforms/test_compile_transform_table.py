import pytest

from streambuild.compiler.compile._helpers.sql_contract import derive_transform_output_columns
from streambuild.compiler.compile._helpers.transforms import compile_transform_table
from streambuild.compiler.shared.models import Column, DesiredTable, ObjectKey
from streambuild.spec.models.steps import TransformStep
from tests.unit.src.streambuild.compiler.compile._helpers.transforms._test_types import (
    CompileTransformTableTestCase,
)
from tests.unit.src.streambuild.compiler.compile._helpers.transforms.helpers import build_transform


@pytest.mark.parametrize(
    "test_case",
    [
        CompileTransformTableTestCase(
            description="copies transform table shape into desired table",
            expected_table_name="tbl__orders_enriched",
            expected_table_key=(None, "table", "tbl__orders_enriched"),
            expected_dep_keys=((None, "table", "raw__orders"),),
            expected_column_names=("order_id", "updated_at", "_replay_landed_at"),
            expected_column_types=("String", "DateTime64(3)", "DateTime64(3)"),
            expected_engine="ReplacingMergeTree(updated_at)",
            expected_order_by=("order_id", "updated_at"),
            expected_partition_by="toYYYYMM(created_at)",
            expected_ttl="toDateTime(created_at) + INTERVAL 30 DAY",
            expected_settings={"index_granularity": "8192"},
        )
    ],
    ids=["copies transform table shape into desired table"],
)
def test_given_transform_when_compiling_transform_table_then_it_returns_expected_desired_table(
    test_case: CompileTransformTableTestCase,
) -> None:
    transform: TransformStep = build_transform()
    assert transform.query is not None
    output_columns: tuple[Column, ...] = derive_transform_output_columns(
        transform.name, transform.query
    )
    target_table_key: ObjectKey = ObjectKey(
        database=None,
        object_type="table",
        name="tbl__orders_enriched",
    )
    source_table_key: ObjectKey = ObjectKey(
        database=None,
        object_type="table",
        name="raw__orders",
    )
    compiled_table: DesiredTable = compile_transform_table(
        transform,
        output_columns,
        key=target_table_key,
        source_table_key=source_table_key,
        bounded_replay_fallback="full_refresh",
    )

    assert compiled_table.name == test_case.expected_table_name
    assert (
        compiled_table.key.database,
        compiled_table.key.object_type,
        compiled_table.key.name,
    ) == test_case.expected_table_key
    assert (
        tuple(
            (dependency.database, dependency.object_type, dependency.name)
            for dependency in compiled_table.deps
        )
        == test_case.expected_dep_keys
    )
    assert (
        tuple(column.name for column in compiled_table.columns) == test_case.expected_column_names
    )
    assert (
        tuple(column.type for column in compiled_table.columns) == test_case.expected_column_types
    )
    assert compiled_table.engine == test_case.expected_engine
    assert compiled_table.order_by == test_case.expected_order_by
    assert compiled_table.partition_by == test_case.expected_partition_by
    assert compiled_table.ttl == test_case.expected_ttl
    assert compiled_table.settings == test_case.expected_settings
