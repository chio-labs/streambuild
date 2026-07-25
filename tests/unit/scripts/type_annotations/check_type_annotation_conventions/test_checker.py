from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.type_annotations.check_type_annotation_conventions import main
from tests.unit.scripts.type_annotations.check_type_annotation_conventions._test_types import (
    CheckCliMainTestCase,
    CheckPathsTestCase,
)
from tests.unit.scripts.type_annotations.check_type_annotation_conventions.helpers import (
    collect_violation_codes,
    compliant_repo_files,
    write_repo_files,
)

TEST_CASES: list[CheckPathsTestCase] = [
    CheckPathsTestCase(
        description="reports no violations for a compliant repo slice",
        repo_files=compliant_repo_files(),
        expected_violation_codes=(),
    ),
    CheckPathsTestCase(
        description="reports missing function parameter and return annotations",
        repo_files=compliant_repo_files()
        | {
            "src/streambuild/example/main.py": dedent(
                """
                def load_example(raw_name):
                    normalized_name: str = raw_name.strip()
                    return normalized_name
                """
            ).strip()
            + "\n"
        },
        expected_violation_codes=("TA001", "TA002"),
    ),
    CheckPathsTestCase(
        description="reports unannotated module, class, and local assignments",
        repo_files=compliant_repo_files()
        | {
            "src/streambuild/example/models.py": dedent(
                """
                class ExampleModel:
                    category = "demo"

                    def __init__(self, name: str) -> None:
                        normalized_name = name.strip()
                        self.name = normalized_name
                """
            ).strip()
            + "\n",
            "tests/unit/src/streambuild/example/test_example.py": dedent(
                """
                import pytest

                from tests.unit.src.streambuild.example._test_types import ExampleTestCase


                TEST_CASES = [
                    ExampleTestCase(
                        description="strips whitespace",
                        raw_name="  demo  ",
                        expected_name="demo",
                    )
                ]


                @pytest.mark.parametrize(
                    "test_case",
                    TEST_CASES,
                    ids=[case.description for case in TEST_CASES],
                )
                def test_given_name_when_normalizing_then_returns_trimmed_value(
                    test_case: ExampleTestCase,
                ) -> None:
                    normalized_name = test_case.raw_name.strip()

                    assert normalized_name == test_case.expected_name
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TA004", "TA005", "TA003", "TA005"),
    ),
    CheckPathsTestCase(
        description="allows self cls destructuring and loop bindings without local annotations",
        repo_files=compliant_repo_files()
        | {
            "src/streambuild/example/models.py": dedent(
                """
                class ExampleModel:
                    name: str

                    def __init__(self, name: str) -> None:
                        self.name = name


                class ExampleFactory:
                    @classmethod
                    def build(cls, raw_name: str) -> ExampleModel:
                        left, right = raw_name.split("-", maxsplit=1)
                        parts = [left, right]
                        for part in parts:
                            _ = part.strip()
                        return ExampleModel(name=raw_name)
                """
            ).strip()
            + "\n"
        },
        expected_violation_codes=("TA005",),
    ),
    CheckPathsTestCase(
        description="ignores enum members without annotations",
        repo_files=compliant_repo_files()
        | {
            "src/streambuild/example/types.py": dedent(
                """
                from enum import StrEnum


                class ExampleMode(StrEnum):
                    AUTO = "auto"
                    NEVER = "never"
                """
            ).strip()
            + "\n"
        },
        expected_violation_codes=(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_repo_slice_when_checking_paths_then_it_reports_expected_violation_codes(
    test_case: CheckPathsTestCase,
    tmp_path: Path,
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    assert collect_violation_codes(tmp_path) == test_case.expected_violation_codes


@pytest.mark.parametrize(
    "test_case",
    [
        CheckCliMainTestCase(
            description="returns zero when no violations are found",
            repo_files=compliant_repo_files(),
            cli_paths=("src", "tests"),
            expected_exit_code=0,
        )
    ],
    ids=["returns zero when no violations are found"],
)
def test_given_repo_slice_when_running_cli_then_it_returns_expected_exit_code(
    test_case: CheckCliMainTestCase,
    tmp_path: Path,
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    previous_cwd: Path = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert main(list(test_case.cli_paths)) == test_case.expected_exit_code
    finally:
        os.chdir(previous_cwd)


@pytest.mark.parametrize(
    "test_case",
    [
        CheckCliMainTestCase(
            description="returns one when violations are found",
            repo_files=compliant_repo_files()
            | {
                "src/streambuild/example/main.py": dedent(
                    """
                    def load_example(raw_name):
                        value = raw_name.strip()
                        return value
                    """
                ).strip()
                + "\n"
            },
            cli_paths=("src", "tests"),
            expected_exit_code=1,
        )
    ],
    ids=["returns one when violations are found"],
)
def test_given_repo_slice_with_violations_when_running_cli_then_it_returns_one(
    test_case: CheckCliMainTestCase,
    tmp_path: Path,
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    previous_cwd: Path = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert main(list(test_case.cli_paths)) == test_case.expected_exit_code
    finally:
        os.chdir(previous_cwd)
