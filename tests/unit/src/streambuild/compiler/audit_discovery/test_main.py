from pathlib import Path

import pytest

from streambuild.compiler.audit_discovery.main.discover_sql_audits import discover_sql_audits
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from tests.unit.src.streambuild.compiler.audit_discovery._test_types import (
    DiscoverGenericSqlAuditsTestCase,
    DiscoverSqlAuditsErrorTestCase,
    DiscoverSqlAuditsTestCase,
    DiscoverSqlAuditsWithMacrosTestCase,
)
from tests.unit.src.streambuild.compiler.audit_discovery.helpers import (
    write_schema_yaml_file,
    write_sql_audit_file,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import write_pipeline_file
from tests.unit.src.streambuild.compiler.macros.helpers import (
    write_macro_file,
    write_project_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverSqlAuditsTestCase(
            description="discovers a minimal audit with default severity",
            relative_file_path="order_events/no_negative_line_totals.sql",
            file_contents="""
        AUDIT ();

        SELECT order_id
        FROM __ref("order_items")
        WHERE line_total < 0
        """,
            expected_audit_names=(None,),
            expected_referenced_model_names=(("order_items",),),
            expected_severities=("error",),
            expected_descriptions=(None,),
        ),
        DiscoverSqlAuditsTestCase(
            description="discovers multiple named audits from one file",
            relative_file_path="singular/order_events/quality.sql",
            file_contents="""
        AUDIT (name: "negative totals", severity: "warning");

        SELECT order_id
        FROM __ref("order_items")
        WHERE line_total < 0;

        AUDIT (name: "missing orders");

        SELECT oi.order_id
        FROM __ref("order_items") AS oi
        LEFT JOIN __ref("orders") AS o ON oi.order_id = o.order_id
        WHERE o.order_id IS NULL
        """,
            expected_audit_names=("negative totals", "missing orders"),
            expected_referenced_model_names=(("order_items",), ("order_items", "orders")),
            expected_severities=("warning", "error"),
            expected_descriptions=(None, None),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_sql_audit_files_when_discovering_then_it_returns_loaded_sql_audits(
    test_case: DiscoverSqlAuditsTestCase,
    tmp_path: Path,
) -> None:
    audits_root: Path = tmp_path / "audits"
    write_sql_audit_file(audits_root / test_case.relative_file_path, test_case.file_contents)

    loaded_audits: list[LoadedSqlAudit] = discover_sql_audits(audits_root)

    assert (
        tuple(loaded_audit.name for loaded_audit in loaded_audits) == test_case.expected_audit_names
    )
    assert (
        tuple(loaded_audit.referenced_model_names for loaded_audit in loaded_audits)
        == test_case.expected_referenced_model_names
    )
    assert (
        tuple(loaded_audit.severity for loaded_audit in loaded_audits)
        == test_case.expected_severities
    )
    assert (
        tuple(loaded_audit.description for loaded_audit in loaded_audits)
        == test_case.expected_descriptions
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverSqlAuditsErrorTestCase(
            description="rejects audits without refs",
            relative_file_path="order_events/no_refs.sql",
            file_contents="""
        AUDIT ();

        SELECT 1
        """,
            expected_error_fragment="must reference at least one model",
        ),
        DiscoverSqlAuditsErrorTestCase(
            description="rejects unsupported severity",
            relative_file_path="order_events/bad_severity.sql",
            file_contents="""
        AUDIT (severity: "info");

        SELECT * FROM __ref("order_items")
        """,
            expected_error_fragment="must define severity as 'error' or 'warning'",
        ),
        DiscoverSqlAuditsErrorTestCase(
            description="rejects source refs",
            relative_file_path="order_events/source_ref.sql",
            file_contents="""
        AUDIT ();

        SELECT * FROM __source("orders")
        """,
            expected_error_fragment=r"__source\(\.\.\.\) is not allowed",
        ),
        DiscoverSqlAuditsErrorTestCase(
            description="rejects unnamed multi audit files",
            relative_file_path="singular/order_events/unnamed_multi.sql",
            file_contents="""
        AUDIT ();
        SELECT * FROM __ref("order_items");

        AUDIT (name: "named");
        SELECT * FROM __ref("orders")
        """,
            expected_error_fragment=(
                r"contains multiple AUDIT\(\.\.\.\) "
                r"blocks; each must define name"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_audit_files_when_discovering_then_it_raises_clear_errors(
    test_case: DiscoverSqlAuditsErrorTestCase,
    tmp_path: Path,
) -> None:
    audits_root: Path = tmp_path / "audits"
    write_sql_audit_file(audits_root / test_case.relative_file_path, test_case.file_contents)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        discover_sql_audits(audits_root)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverSqlAuditsWithMacrosTestCase(
            description="expands project macros in audit bodies",
            macro_file_contents="""
            def negative_predicate() -> str:
                return "line_total < 0"
            """,
            audit_file_contents="""
            AUDIT ();

            SELECT order_id
            FROM __ref("order_items")
            WHERE @negative_predicate()
            """,
            expected_query_fragment="line_total < 0",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_audit_macros_when_discovering_then_it_expands_audit_body(
    test_case: DiscoverSqlAuditsWithMacrosTestCase,
    tmp_path: Path,
) -> None:
    audits_root: Path = tmp_path / "audits"
    write_project_file(tmp_path)
    write_macro_file(tmp_path, "audit_helpers.py", test_case.macro_file_contents)
    write_sql_audit_file(
        audits_root / "order_events/macro_audit.sql", test_case.audit_file_contents
    )

    loaded_audits: list[LoadedSqlAudit] = discover_sql_audits(audits_root)

    assert test_case.expected_query_fragment in loaded_audits[0].query


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverGenericSqlAuditsTestCase(
            description="renders generic sql audits from schema attached instances",
            definition_file_contents="""
            AUDIT ();

            SELECT @column
            FROM __ref("@model")
            WHERE @column IS NULL
            """,
            schema_file_contents="""
            models:
              - name: order_items
                columns:
                  - name: order_id
                    audits:
                      - not_null:
                          name: order items order id not null
                          severity: warning
            """,
            expected_name="order items order id not null",
            expected_query_fragment='FROM __ref("order_items")',
            expected_referenced_model_names=("order_items",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generic_sql_audits_when_discovering_then_it_renders_concrete_audits(
    test_case: DiscoverGenericSqlAuditsTestCase,
    tmp_path: Path,
) -> None:
    audits_root: Path = tmp_path / "audits"
    write_pipeline_file(
        tmp_path / "pipelines" / "order_events" / "pipeline.yml",
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_sql_audit_file(
        audits_root / "generic" / "not_null.sql", test_case.definition_file_contents
    )
    write_schema_yaml_file(
        tmp_path / "pipelines" / "order_events" / "schema.yml",
        test_case.schema_file_contents,
    )

    loaded_audits: list[LoadedSqlAudit] = discover_sql_audits(audits_root)

    assert loaded_audits[0].name == test_case.expected_name
    assert test_case.expected_query_fragment in loaded_audits[0].query
    assert loaded_audits[0].referenced_model_names == test_case.expected_referenced_model_names
