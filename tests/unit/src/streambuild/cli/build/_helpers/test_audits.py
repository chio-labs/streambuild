from pathlib import Path

import pytest

from streambuild.cli.build._helpers.audits import select_standard_build_audits
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from tests.unit.src.streambuild.cli.build._helpers._test_types import (
    StandardBuildAuditSelectionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StandardBuildAuditSelectionTestCase(
            description="selected closure keeps only fully covered audits",
            audit_refs_by_name=(
                ("alpha_only", ("alpha",)),
                ("beta_only", ("beta",)),
                ("descendants", ("gamma", "delta")),
                ("partial", ("alpha", "delta")),
                ("global", ()),
            ),
            execution_model_names=frozenset({"beta", "gamma", "delta"}),
            full_build=False,
            expected_audit_names=("beta_only", "descendants", "global"),
        ),
        StandardBuildAuditSelectionTestCase(
            description="full build keeps every project audit",
            audit_refs_by_name=(
                ("alpha_only", ("alpha",)),
                ("partial", ("alpha", "delta")),
            ),
            execution_model_names=frozenset({"alpha", "beta", "gamma", "delta"}),
            full_build=True,
            expected_audit_names=("alpha_only", "partial"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_execution_scope_when_selecting_build_audits_then_only_covered_audits_run(
    test_case: StandardBuildAuditSelectionTestCase,
) -> None:
    audits: tuple[LoadedSqlAudit, ...] = tuple(
        LoadedSqlAudit(
            file_path=Path(f"audits/{name}.sql"),
            query="SELECT 1 WHERE 0",
            referenced_model_names=refs,
            name=name,
        )
        for name, refs in test_case.audit_refs_by_name
    )

    selected: tuple[LoadedSqlAudit, ...] = select_standard_build_audits(
        audits=audits,
        execution_model_names=test_case.execution_model_names,
        full_build=test_case.full_build,
    )

    assert tuple(audit.name for audit in selected) == test_case.expected_audit_names
