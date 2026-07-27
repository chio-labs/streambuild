"""Deterministic text assembly for compile artifacts."""

import json

from streambuild.compiler.test_discovery.models import SqlTestCase


def normalized_sql(sql: str) -> str:
    return sql.rstrip() + "\n"


def workflow_sql(*, entries: tuple[tuple[str, str], ...]) -> str:
    return (
        "\n\n".join(
            f"-- {file_name}\n{contents.rstrip()}" for file_name, contents in entries
        ).rstrip()
        + "\n"
    )


def workflow_json(*, pipeline_name: str, entries: tuple[tuple[str, str], ...]) -> str:
    payload: dict[str, object] = {
        "pipeline": pipeline_name,
        "steps": tuple({"file": f"steps/{file_name}"} for file_name, _contents in entries),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def static_test_sql(*, test_case: SqlTestCase) -> str:
    if len(test_case.target_cases) == 1:
        return normalized_sql(test_case.target_cases[0].query)
    ctes: tuple[str, ...] = tuple(
        f"__streambuild_target_{index} AS (\n{target_case.query.rstrip()}\n)"
        for index, target_case in enumerate(test_case.target_cases, start=1)
    )
    comparisons: tuple[str, ...] = tuple(
        "SELECT "
        f"'{target_case.target_model_name.replace("'", "''")}' AS _target, "
        f"count() AS _difference_count FROM __streambuild_target_{index}"
        for index, target_case in enumerate(test_case.target_cases, start=1)
    )
    return "WITH\n" + ",\n".join(ctes) + "\n" + "\nUNION ALL\n".join(comparisons) + "\n"
