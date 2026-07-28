"""Deterministic text assembly for compile artifacts."""

import json

from streambuild.compiler.testing.models import SqlTestCase


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
    return normalized_sql(test_case.query)
