"""Apache-2.0: SQLBuild compile/_helpers/sql_tests/core.py classification@7e3b2f854f05."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.discovery.types import SqlRelationType
from streambuild.compiler.sql_analysis.main._extract_references import extract_references
from streambuild.compiler.sql_analysis.models import SqlReference
from streambuild.compiler.test_discovery.constants import (
    ASSERT_CTE_PREFIX,
    EXPECTED_CTE_PREFIX,
    MACRO_ACTUAL_CTE_NAME,
    MACRO_EXPECTED_CTE_NAME,
    MODEL_MODE_CTE_PREFIXES,
    REF_CTE_PREFIX,
    RESERVED_SQL_TEST_CTE_NAMES,
    SOURCE_CTE_PREFIX,
    UNSUPPORTED_MODE_CTE_NAMES,
    UNSUPPORTED_MODE_CTE_PREFIXES,
)
from streambuild.compiler.test_discovery.exceptions import SqlTestParseError
from streambuild.compiler.test_discovery.models import (
    SqlTestCte,
    SqlTestMacroPayload,
    SqlTestMock,
    SqlTestModelPayload,
)
from streambuild.compiler.test_discovery.types import SqlTestMode


def classify_model_test_ctes(
    *, ctes: tuple[SqlTestCte, ...], file_path: Path
) -> tuple[tuple[SqlTestCte, ...], SqlTestModelPayload]:
    """Split model-mode CTEs into helpers, mocks, expectations, and assertions."""

    authored_ctes: list[SqlTestCte] = []
    mocks: list[SqlTestMock] = []
    expected_targets: list[SqlTestCte] = []
    assertions: list[SqlTestCte] = []
    cte: SqlTestCte
    for cte in ctes:
        _reject_unsupported_cte(cte=cte, file_path=file_path, mode=SqlTestMode.MODEL)
        _reject_macro_mode_cte(cte=cte, file_path=file_path)
        mock: SqlTestMock | None = _mock_for(cte=cte, file_path=file_path)
        if mock is not None:
            authored_ctes.append(cte)
            mocks.append(mock)
            continue
        if cte.name.startswith(EXPECTED_CTE_PREFIX):
            _require_suffix(cte=cte, prefix=EXPECTED_CTE_PREFIX, file_path=file_path)
            expected_targets.append(cte)
            continue
        if cte.name.startswith(ASSERT_CTE_PREFIX):
            _require_suffix(cte=cte, prefix=ASSERT_CTE_PREFIX, file_path=file_path)
            assertions.append(cte)
            continue
        _reject_reserved_cte(cte=cte, file_path=file_path)
        authored_ctes.append(cte)
    _validate_model_completeness(
        mocks=tuple(mocks),
        expected_targets=tuple(expected_targets),
        assertions=tuple(assertions),
        file_path=file_path,
    )
    return tuple(authored_ctes), SqlTestModelPayload(
        mocks=tuple(mocks),
        expected_targets=tuple(expected_targets),
        assertions=tuple(assertions),
        assertion_reference_names=_assertion_reference_names(assertions=tuple(assertions)),
    )


def classify_macro_test_ctes(
    *, ctes: tuple[SqlTestCte, ...], file_path: Path
) -> tuple[tuple[SqlTestCte, ...], SqlTestMacroPayload]:
    """Split macro-mode CTEs into helper CTEs and the actual/expected pair."""

    authored_ctes: list[SqlTestCte] = []
    actual_cte: SqlTestCte | None = None
    expected_cte: SqlTestCte | None = None
    cte: SqlTestCte
    for cte in ctes:
        _reject_unsupported_cte(cte=cte, file_path=file_path, mode=SqlTestMode.MACRO)
        if cte.name == MACRO_ACTUAL_CTE_NAME:
            actual_cte = cte
            continue
        if cte.name == MACRO_EXPECTED_CTE_NAME:
            expected_cte = cte
            continue
        _reject_model_mode_cte(cte=cte, file_path=file_path)
        _reject_reserved_cte(cte=cte, file_path=file_path)
        authored_ctes.append(cte)
    if actual_cte is None or expected_cte is None:
        raise SqlTestParseError(
            f"SQL test '{file_path}' mode 'macro' must define exactly one "
            f"{MACRO_ACTUAL_CTE_NAME} CTE and exactly one {MACRO_EXPECTED_CTE_NAME} CTE"
        )
    return tuple(authored_ctes), SqlTestMacroPayload(actual=actual_cte, expected=expected_cte)


def _mock_for(*, cte: SqlTestCte, file_path: Path) -> SqlTestMock | None:
    if cte.name.startswith(REF_CTE_PREFIX):
        _require_suffix(cte=cte, prefix=REF_CTE_PREFIX, file_path=file_path)
        return SqlTestMock(
            cte_name=cte.name,
            name=cte.name.removeprefix(REF_CTE_PREFIX),
            relation_type=SqlRelationType.REF,
            query=cte.query,
        )
    if cte.name.startswith(SOURCE_CTE_PREFIX):
        _require_suffix(cte=cte, prefix=SOURCE_CTE_PREFIX, file_path=file_path)
        return SqlTestMock(
            cte_name=cte.name,
            name=cte.name.removeprefix(SOURCE_CTE_PREFIX),
            relation_type=SqlRelationType.SOURCE,
            query=cte.query,
        )
    return None


def _validate_model_completeness(
    *,
    mocks: tuple[SqlTestMock, ...],
    expected_targets: tuple[SqlTestCte, ...],
    assertions: tuple[SqlTestCte, ...],
    file_path: Path,
) -> None:
    if not mocks:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must define at least one __ref__* or __source__* mock CTE"
        )
    if not expected_targets and not assertions:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must define at least one __expected__<model> or "
            "__assert__<assertion> CTE"
        )


def _assertion_reference_names(*, assertions: tuple[SqlTestCte, ...]) -> tuple[str, ...]:
    names: list[str] = []
    assertion: SqlTestCte
    for assertion in assertions:
        reference: SqlReference
        for reference in extract_references(assertion.query):
            if reference.relation_type == SqlRelationType.REF:
                names.append(reference.name)
    return tuple(dict.fromkeys(names))


def _reject_unsupported_cte(*, cte: SqlTestCte, file_path: Path, mode: SqlTestMode) -> None:
    if cte.name in UNSUPPORTED_MODE_CTE_NAMES or cte.name.startswith(UNSUPPORTED_MODE_CTE_PREFIXES):
        raise SqlTestParseError(
            f"SQL test '{file_path}' mode '{mode.value}' does not support CTE '{cte.name}'; "
            "StreamBuild supports __source__, __ref__, __expected__, __assert__, "
            "__macro_actual__, and __macro_expected__"
        )


def _reject_macro_mode_cte(*, cte: SqlTestCte, file_path: Path) -> None:
    if cte.name in {MACRO_ACTUAL_CTE_NAME, MACRO_EXPECTED_CTE_NAME}:
        raise SqlTestParseError(
            f"SQL test '{file_path}' is mode 'model' but defines macro-test CTE "
            f"'{cte.name}'; use TEST (mode: macro)"
        )


def _reject_model_mode_cte(*, cte: SqlTestCte, file_path: Path) -> None:
    if cte.name.startswith(MODEL_MODE_CTE_PREFIXES):
        raise SqlTestParseError(
            f"SQL test '{file_path}' is mode 'macro' but defines model-test CTE '{cte.name}'"
        )


def _reject_reserved_cte(*, cte: SqlTestCte, file_path: Path) -> None:
    if cte.name in RESERVED_SQL_TEST_CTE_NAMES:
        raise SqlTestParseError(
            f"SQL test '{file_path}' uses reserved helper CTE name '{cte.name}'"
        )


def _require_suffix(*, cte: SqlTestCte, prefix: str, file_path: Path) -> None:
    if not cte.name.removeprefix(prefix):
        raise SqlTestParseError(
            f"SQL test '{file_path}' must use {prefix}<name> to identify a target"
        )
