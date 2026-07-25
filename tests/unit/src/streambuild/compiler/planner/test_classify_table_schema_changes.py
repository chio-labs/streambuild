import pytest

from streambuild.compiler.actual_state.models import ActualTable
from streambuild.compiler.planner.constants import (
    PLANNED_CHANGE_TYPE_NO_OP,
    TABLE_SCHEMA_CHANGE_KIND_BREAKING,
    TABLE_SCHEMA_CHANGE_KIND_NON_BREAKING,
    TABLE_SCHEMA_SEED_COMPATIBILITY_NON_SEEDABLE,
    TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE,
)
from streambuild.compiler.planner.helpers.diff import (
    classify_object_change_type,
    classify_table_schema_change_kind,
    classify_table_seed_compatibility,
)
from streambuild.compiler.shared.models import (
    Column,
    DesiredTable,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from tests.unit.src.streambuild.compiler.planner._test_types import (
    PlannerTableSchemaClassificationTestCase,
)

TEST_CASES: list[PlannerTableSchemaClassificationTestCase] = [
    PlannerTableSchemaClassificationTestCase(
        description="classifies added column as non-breaking and seedable",
        actual_columns=(("order_id", "UInt64"),),
        desired_columns=(("order_id", "UInt64"), ("region", "String")),
        expected_schema_change_kind=TABLE_SCHEMA_CHANGE_KIND_NON_BREAKING,
        expected_seed_compatibility=TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="classifies removed column as breaking and seedable",
        actual_columns=(("order_id", "UInt64"), ("region", "String")),
        desired_columns=(("order_id", "UInt64"),),
        expected_schema_change_kind=TABLE_SCHEMA_CHANGE_KIND_BREAKING,
        expected_seed_compatibility=TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="classifies type change as breaking and non-seedable",
        actual_columns=(("order_id", "UInt64"),),
        desired_columns=(("order_id", "String"),),
        expected_schema_change_kind=TABLE_SCHEMA_CHANGE_KIND_BREAKING,
        expected_seed_compatibility=TABLE_SCHEMA_SEED_COMPATIBILITY_NON_SEEDABLE,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="classifies add and remove combination as breaking and seedable",
        actual_columns=(("order_id", "UInt64"), ("region", "String")),
        desired_columns=(("order_id", "UInt64"), ("country", "String")),
        expected_schema_change_kind=TABLE_SCHEMA_CHANGE_KIND_BREAKING,
        expected_seed_compatibility=TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="treats equivalent clickhouse type casing as no-op",
        actual_columns=(("observed_day", "Date"),),
        desired_columns=(("observed_day", "DATE"),),
        expected_schema_change_kind=None,
        expected_seed_compatibility=None,
        expected_change_type=PLANNED_CHANGE_TYPE_NO_OP,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="treats decimal spacing differences as no-op",
        actual_columns=(("order_total", "Decimal(18,2)"),),
        desired_columns=(("order_total", "Decimal(18, 2)"),),
        expected_schema_change_kind=None,
        expected_seed_compatibility=None,
        expected_change_type=PLANNED_CHANGE_TYPE_NO_OP,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="treats nested nullable low cardinality casing as no-op",
        actual_columns=(("region", "Nullable(LowCardinality(String))"),),
        desired_columns=(("region", "nullable(lowcardinality(string))"),),
        expected_schema_change_kind=None,
        expected_seed_compatibility=None,
        expected_change_type=PLANNED_CHANGE_TYPE_NO_OP,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="treats datetime precision spacing as no-op",
        actual_columns=(("observed_at", "DateTime64(3)"),),
        desired_columns=(("observed_at", "DateTime64( 3 )"),),
        expected_schema_change_kind=None,
        expected_seed_compatibility=None,
        expected_change_type=PLANNED_CHANGE_TYPE_NO_OP,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="treats array inner type casing as no-op",
        actual_columns=(("headers", "Array(String)"),),
        desired_columns=(("headers", "array(string)"),),
        expected_schema_change_kind=None,
        expected_seed_compatibility=None,
        expected_change_type=PLANNED_CHANGE_TYPE_NO_OP,
    ),
    PlannerTableSchemaClassificationTestCase(
        description="still treats real nested type changes as breaking",
        actual_columns=(("region", "Nullable(String)"),),
        desired_columns=(("region", "Nullable(FixedString(2))"),),
        expected_schema_change_kind=TABLE_SCHEMA_CHANGE_KIND_BREAKING,
        expected_seed_compatibility=TABLE_SCHEMA_SEED_COMPATIBILITY_NON_SEEDABLE,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_table_column_changes_when_classifying_then_it_returns_expected_schema_metadata(
    test_case: PlannerTableSchemaClassificationTestCase,
) -> None:
    actual_table: ActualTable = ActualTable(
        key=ObjectKey(None, "table", "tbl__orders_enriched"),
        spec=TableSpec(
            columns=tuple(Column(name, type_name) for name, type_name in test_case.actual_columns),
            storage=TableStorage(engine="MergeTree()", order_by=("order_id",)),
        ),
    )
    desired_table: DesiredTable = DesiredTable(
        key=ObjectKey(None, "table", "tbl__orders_enriched"),
        deps=(),
        spec=TableSpec(
            columns=tuple(Column(name, type_name) for name, type_name in test_case.desired_columns),
            storage=TableStorage(engine="MergeTree()", order_by=("order_id",)),
        ),
    )

    assert (
        classify_object_change_type(desired_table, actual_table) == test_case.expected_change_type
    )
    assert (
        classify_table_schema_change_kind(desired_table, actual_table)
        == test_case.expected_schema_change_kind
    )
    assert (
        classify_table_seed_compatibility(desired_table, actual_table)
        == test_case.expected_seed_compatibility
    )
