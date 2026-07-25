from pathlib import Path

import pytest

from streambuild.cli.commands.main.audit._helpers.selection import select_loaded_sql_audits
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.shared.models import LoadedSqlAudit
from tests.unit.src.streambuild.cli.commands.main.audit._helpers._test_types import (
    CliAuditSelectionErrorTestCase,
    CliAuditSelectionTestCase,
)
from tests.unit.src.streambuild.cli.commands.main.shared.helpers import (
    compile_selector_project_pipelines,
)

TEST_CASES: list[CliAuditSelectionTestCase] = [
    CliAuditSelectionTestCase(
        description="bare model selector matches audits that reference that model",
        selectors=("orders_clean",),
        audit_model_names=(("orders_clean",), ("orders_enriched",), ("payments_enriched",)),
        expected_selected_indexes=(0,),
    ),
    CliAuditSelectionTestCase(
        description="upstream selector includes audits for upstream models too",
        selectors=("+orders_enriched",),
        audit_model_names=(("orders",), ("orders_clean",), ("orders_enriched",)),
        expected_selected_indexes=(1, 2),
    ),
    CliAuditSelectionTestCase(
        description="pipeline selector includes audits for all pipeline models",
        selectors=("pipeline:payments",),
        audit_model_names=(("orders_clean",), ("payments_enriched",)),
        expected_selected_indexes=(1,),
    ),
]

ERROR_TEST_CASES: list[CliAuditSelectionErrorTestCase] = [
    CliAuditSelectionErrorTestCase(
        description="rejects unknown selector namespaces",
        selectors=("tag:finance",),
        expected_error_fragment="Unsupported audit selector namespace 'tag'",
    ),
    CliAuditSelectionErrorTestCase(
        description="rejects malformed plus syntax",
        selectors=("orders+",),
        expected_error_fragment="Unsupported audit selector syntax",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_valid_audit_selectors_when_selecting_then_it_returns_matching_audits(
    test_case: CliAuditSelectionTestCase,
) -> None:
    compiled_pipelines: tuple[CompiledPipeline, ...] = compile_selector_project_pipelines()
    loaded_audits: tuple[LoadedSqlAudit, ...] = tuple(
        LoadedSqlAudit(
            file_path=Path(f"audits/audit_{index}.sql"),
            query="SELECT 1",
            referenced_model_names=model_names,
        )
        for index, model_names in enumerate(test_case.audit_model_names)
    )

    selected_audits: tuple[LoadedSqlAudit, ...] = select_loaded_sql_audits(
        loaded_audits=loaded_audits,
        compiled_pipelines=compiled_pipelines,
        selectors=test_case.selectors,
    )

    assert tuple(loaded_audits.index(selected_audit) for selected_audit in selected_audits) == (
        test_case.expected_selected_indexes
    )


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_audit_selectors_when_selecting_then_it_raises_clear_errors(
    test_case: CliAuditSelectionErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        select_loaded_sql_audits(
            loaded_audits=(),
            compiled_pipelines=compile_selector_project_pipelines(),
            selectors=test_case.selectors,
        )
