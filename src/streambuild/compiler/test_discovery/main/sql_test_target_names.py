"""Public accessor for the logical model targets of one discovered SQL test."""

from __future__ import annotations

from streambuild.compiler.test_discovery.constants import EXPECTED_CTE_PREFIX
from streambuild.compiler.test_discovery.models import (
    LoadedSqlTest,
    SqlTestModelPayload,
)


def sql_test_target_names(*, loaded_test: LoadedSqlTest) -> tuple[str, ...]:
    """Return the logical model names one test evaluates or asserts on."""

    payload: object = loaded_test.payload
    if not isinstance(payload, SqlTestModelPayload):
        return ()
    return tuple(
        dict.fromkeys(
            (
                *(
                    expected_target.name.removeprefix(EXPECTED_CTE_PREFIX)
                    for expected_target in payload.expected_targets
                ),
                *payload.assertion_reference_names,
            )
        )
    )
