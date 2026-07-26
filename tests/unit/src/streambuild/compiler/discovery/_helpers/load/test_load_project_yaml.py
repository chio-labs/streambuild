from pathlib import Path

import pytest

from streambuild.compiler.discovery._helpers.load import load_project_yaml
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.models import Project
from tests.unit.src.streambuild.compiler.discovery._helpers.load._test_types import (
    LoadProjectAdapterConfigErrorTestCase,
    LoadProjectAdapterConfigTestCase,
    LoadProjectCredentialRedactionTestCase,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectAdapterConfigTestCase(
            description="defaults to the clickhouse adapter when no adapter is declared",
            project_file_contents="default_database: analytics",
            expected_version=None,
            expected_adapter="clickhouse",
        ),
        LoadProjectAdapterConfigTestCase(
            description="reads the declared version two marker and adapter name",
            project_file_contents="""
            version: 2
            adapter: clickhouse
            default_database: analytics
            """,
            expected_version=2,
            expected_adapter="clickhouse",
        ),
        LoadProjectAdapterConfigTestCase(
            description="retains an unregistered adapter name for later resolution",
            project_file_contents="""
            version: 2
            adapter: duckdb
            """,
            expected_version=2,
            expected_adapter="duckdb",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_file_when_loading_then_it_resolves_version_and_adapter(
    test_case: LoadProjectAdapterConfigTestCase,
    tmp_path: Path,
) -> None:
    project_file_path: Path = tmp_path / "streambuild_project.yml"
    write_pipeline_file(project_file_path, test_case.project_file_contents)

    project: Project = load_project_yaml(project_file_path)

    assert project.version == test_case.expected_version
    assert project.adapter == test_case.expected_adapter


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectAdapterConfigErrorTestCase(
            description="rejects an unsupported project version",
            project_file_contents="version: 3",
            expected_error_fragment="declares unsupported version 3",
        ),
        LoadProjectAdapterConfigErrorTestCase(
            description="rejects a non-integer project version",
            project_file_contents="version: two",
            expected_error_fragment="must define version as the integer 2",
        ),
        LoadProjectAdapterConfigErrorTestCase(
            description="rejects an empty adapter name",
            project_file_contents="adapter: ''",
            expected_error_fragment="must define adapter as a non-empty string",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_adapter_configuration_when_loading_then_it_fails_with_source_path(
    test_case: LoadProjectAdapterConfigErrorTestCase,
    tmp_path: Path,
) -> None:
    project_file_path: Path = tmp_path / "streambuild_project.yml"
    write_pipeline_file(project_file_path, test_case.project_file_contents)

    with pytest.raises(PipelineDiscoveryError) as error_info:
        load_project_yaml(project_file_path)

    assert test_case.expected_error_fragment in str(error_info.value)
    assert str(project_file_path) in str(error_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectCredentialRedactionTestCase(
            description="does not expose authored connection credentials through project repr",
            project_file_contents="""
            clickhouse:
              host: localhost
              port: 8123
              username: streambuild
              password: project-secret
            """,
            expected_absent_repr_fragment="project-secret",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_credentials_when_loading_then_project_repr_does_not_expose_them(
    test_case: LoadProjectCredentialRedactionTestCase,
    tmp_path: Path,
) -> None:
    project_file_path: Path = tmp_path / "streambuild_project.yml"
    write_pipeline_file(project_file_path, test_case.project_file_contents)

    project: Project = load_project_yaml(project_file_path)

    assert test_case.expected_absent_repr_fragment not in repr(project)
