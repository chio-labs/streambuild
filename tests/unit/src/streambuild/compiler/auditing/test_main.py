from pathlib import Path

import pytest

from streambuild.compiler.shared.models import LoadedSqlAudit
from tests.unit.src.streambuild.compiler.auditing._test_types import (
    ValidateSqlAuditsErrorTestCase,
    ValidateSqlAuditsTestCase,
)
from tests.unit.src.streambuild.compiler.auditing.helpers import validate_project_sql_audits

ERROR_TEST_CASES: list[ValidateSqlAuditsErrorTestCase] = [
    ValidateSqlAuditsErrorTestCase(
        description="rejects unknown audit model refs",
        audit_file_contents="""
        AUDIT ();

        SELECT * FROM __ref("missing_model")
        """,
        expected_error_fragment="references unknown models: missing_model",
    ),
    ValidateSqlAuditsErrorTestCase(
        description="rejects unknown generic audit model refs",
        audit_file_contents="",
        expected_error_fragment="references unknown models: missing_model",
        generic_definition_file_contents="""
        AUDIT ();

        SELECT *
        FROM __ref("@model") AS source_model
        INNER JOIN __ref("@other_model") AS other_model ON 1 = 1
        """,
        schema_file_contents="""
        models:
          - name: order_items
            audits:
              - not_null:
                  other_model: missing_model
                  name: missing model generic audit
        """,
    ),
]

TEST_CASES: list[ValidateSqlAuditsTestCase] = [
    ValidateSqlAuditsTestCase(
        description="returns validated audits when all refs exist",
        audit_file_contents="""
        AUDIT (severity: "warning");

        SELECT * FROM __ref("order_items") WHERE line_total < 0
        """,
        expected_referenced_model_names=("order_items",),
        expected_severity="warning",
    ),
    ValidateSqlAuditsTestCase(
        description="returns validated rendered generic audits when all refs exist",
        audit_file_contents="",
        generic_definition_file_contents="""
        AUDIT ();

        SELECT @column FROM __ref("@model") WHERE @column IS NULL
        """,
        schema_file_contents="""
        models:
          - name: order_items
            columns:
              - name: order_id
                audits:
                  - not_null:
                      name: generic order id audit
        """,
        expected_referenced_model_names=("order_items",),
        expected_severity="error",
        expected_name="generic order id audit",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_sql_audits_when_validating_then_it_raises_clear_errors(
    test_case: ValidateSqlAuditsErrorTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        validate_project_sql_audits(
            tmp_path=tmp_path,
            audit_file_contents=test_case.audit_file_contents,
            generic_definition_file_contents=test_case.generic_definition_file_contents,
            schema_file_contents=test_case.schema_file_contents,
        )


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_valid_sql_audits_when_validating_then_it_returns_loaded_audits(
    test_case: ValidateSqlAuditsTestCase,
    tmp_path: Path,
) -> None:
    loaded_audits: tuple[LoadedSqlAudit, ...] = validate_project_sql_audits(
        tmp_path=tmp_path,
        audit_file_contents=test_case.audit_file_contents,
        generic_definition_file_contents=test_case.generic_definition_file_contents,
        schema_file_contents=test_case.schema_file_contents,
    )

    assert loaded_audits[0].referenced_model_names == test_case.expected_referenced_model_names
    assert loaded_audits[0].severity == test_case.expected_severity
    assert loaded_audits[0].name == test_case.expected_name
