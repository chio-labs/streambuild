from pathlib import Path

import pytest

from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.test._helpers.selection import select_loaded_sql_tests
from streambuild.compiler.test_discovery.models import LoadedSqlTest
from tests.unit.src.streambuild.cli.test._helpers._test_types import (
    SelectLoadedSqlTestsErrorTestCase,
    SelectLoadedSqlTestsTestCase,
)
from tests.unit.src.streambuild.cli.test._helpers.helpers import (
    build_selector_project_compiled_pipelines,
    build_selector_project_loaded_tests,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SelectLoadedSqlTestsTestCase(
            description="bare model selector includes tests for that target only",
            selectors=("orders_clean",),
            paths=(),
            expected_target_model_names=("orders_clean",),
        ),
        SelectLoadedSqlTestsTestCase(
            description="pipeline selector includes tests for all models in that pipeline",
            selectors=("pipeline:orders",),
            paths=(),
            expected_target_model_names=("orders_clean", "orders_enriched"),
        ),
        SelectLoadedSqlTestsTestCase(
            description="downstream plus selector includes downstream target tests",
            selectors=("orders_clean+",),
            paths=(),
            expected_target_model_names=("orders_clean", "orders_enriched"),
        ),
        SelectLoadedSqlTestsTestCase(
            description="upstream plus selector includes upstream target tests",
            selectors=("+orders_enriched",),
            paths=(),
            expected_target_model_names=("orders_clean", "orders_enriched"),
        ),
        SelectLoadedSqlTestsTestCase(
            description="multiple selectors union correctly",
            selectors=("orders_clean", "pipeline:payments"),
            paths=(),
            expected_target_model_names=("orders_clean", "payments_enriched"),
        ),
        SelectLoadedSqlTestsTestCase(
            description="graph and plain selectors union correctly",
            selectors=("orders_clean+", "payments_enriched"),
            paths=(),
            expected_target_model_names=(
                "orders_clean",
                "orders_enriched",
                "payments_enriched",
            ),
        ),
        SelectLoadedSqlTestsTestCase(
            description="path selections union with selector matches",
            selectors=("payments_enriched",),
            paths=("tests/orders/test_orders_enriched.sql",),
            expected_target_model_names=("orders_enriched", "payments_enriched"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_test_selectors_when_selecting_then_it_returns_expected_targets(
    test_case: SelectLoadedSqlTestsTestCase,
    tmp_path: Path,
) -> None:
    loaded_tests: tuple[LoadedSqlTest, ...] = build_selector_project_loaded_tests(tmp_path)

    selected_tests: tuple[LoadedSqlTest, ...] = select_loaded_sql_tests(
        loaded_tests=loaded_tests,
        compiled_pipelines=build_selector_project_compiled_pipelines(),
        selectors=test_case.selectors,
        paths=tuple(Path(path) for path in test_case.paths),
        project_dir=tmp_path,
    )

    selected_target_model_names: tuple[str, ...] = tuple(
        sorted(
            {
                expected_target.name.removeprefix("__expected__")
                for test in selected_tests
                for expected_target in test.expected_targets
            }
        )
    )

    assert selected_target_model_names == tuple(sorted(test_case.expected_target_model_names))


@pytest.mark.parametrize(
    "test_case",
    [
        SelectLoadedSqlTestsErrorTestCase(
            description="invalid selector syntax fails clearly",
            selectors=("++orders_clean",),
            paths=(),
            expected_error_fragment="Unsupported test selector syntax",
        ),
        SelectLoadedSqlTestsErrorTestCase(
            description="unknown selector namespace fails clearly",
            selectors=("tag:finance",),
            paths=(),
            expected_error_fragment="Unsupported test selector namespace 'tag'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_test_selectors_when_selecting_then_it_raises_clear_errors(
    test_case: SelectLoadedSqlTestsErrorTestCase,
    tmp_path: Path,
) -> None:
    loaded_tests: tuple[LoadedSqlTest, ...] = build_selector_project_loaded_tests(tmp_path)

    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        select_loaded_sql_tests(
            loaded_tests=loaded_tests,
            compiled_pipelines=build_selector_project_compiled_pipelines(),
            selectors=test_case.selectors,
            paths=tuple(Path(path) for path in test_case.paths),
            project_dir=tmp_path,
        )
