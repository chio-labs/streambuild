from pathlib import Path
from textwrap import dedent


def write_sql_audit_file(file_path: Path, contents: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")


def write_schema_yaml_file(file_path: Path, contents: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")
