import tomllib
from pathlib import Path
from typing import cast

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tests.unit.src.streambuild.compiler.sql_analysis._test_types import (
    SqlAnalysisBoundaryTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlAnalysisBoundaryTestCase(
            description="keeps Polyglot imports and AST objects inside sql analysis",
            forbidden_import="polyglot_sql",
            removed_dependency_name="sqlglot",
            expected_outside_import_paths=(),
            expected_removed_source_paths=(),
            expected_retired_path_exists=False,
            expected_dependency_spec="polyglot-sql>=0.5.10",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_source_when_checking_polyglot_boundary_then_only_analysis_package_imports_it(
    test_case: SqlAnalysisBoundaryTestCase,
) -> None:
    source_root: Path = Path("src/streambuild")
    analysis_root: Path = source_root / "compiler" / "sql_analysis"
    runtime_files: tuple[Path, ...] = tuple(source_root.rglob("*.py"))
    outside_files: tuple[Path, ...] = tuple(
        filter(lambda path: analysis_root not in path.parents, runtime_files)
    )
    outside_import_paths: tuple[str, ...] = tuple(
        path.as_posix()
        for path in filter(
            lambda path: test_case.forbidden_import in path.read_text(),
            outside_files,
        )
    )
    removed_source_paths: tuple[str, ...] = tuple(
        path.as_posix()
        for path in filter(
            lambda path: test_case.removed_dependency_name in path.read_text(),
            runtime_files,
        )
    )
    retired_path: Path = source_root / "compiler" / "compile" / "_helpers" / "refs.py"
    project_configuration: dict[str, object] = tomllib.loads(Path("pyproject.toml").read_text())
    project: dict[str, object] = cast(dict[str, object], project_configuration["project"])
    dependencies: list[str] = cast(list[str], project["dependencies"])

    assert outside_import_paths == test_case.expected_outside_import_paths
    assert removed_source_paths == test_case.expected_removed_source_paths
    assert retired_path.exists() is test_case.expected_retired_path_exists
    assert test_case.expected_dependency_spec in dependencies
    lock_contents: str = Path("uv.lock").read_text()

    assert canonicalize_name(test_case.removed_dependency_name) not in tuple(
        canonicalize_name(Requirement(dependency).name) for dependency in dependencies
    )
    assert f'name = "{test_case.removed_dependency_name}"' not in lock_contents
    assert test_case.expected_dependency_spec.split(">=")[0] in lock_contents
