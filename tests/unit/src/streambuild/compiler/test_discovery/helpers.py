from pathlib import Path
from textwrap import dedent


def write_sql_test_file(file_path: Path, contents: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")
