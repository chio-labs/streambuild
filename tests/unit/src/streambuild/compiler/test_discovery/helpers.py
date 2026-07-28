from pathlib import Path
from textwrap import dedent
from typing import cast

from streambuild.compiler.test_discovery.models import (
    LoadedSqlTest,
    SqlTestMacroPayload,
    SqlTestModelPayload,
)


def write_sql_test_file(file_path: Path, contents: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")


def model_payload(loaded_test: LoadedSqlTest) -> SqlTestModelPayload:
    return cast(SqlTestModelPayload, loaded_test.payload)


def macro_payload(loaded_test: LoadedSqlTest) -> SqlTestMacroPayload:
    return cast(SqlTestMacroPayload, loaded_test.payload)
