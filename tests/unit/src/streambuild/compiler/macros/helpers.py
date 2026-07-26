from pathlib import Path
from textwrap import dedent


def write_project_file(project_dir: Path) -> Path:
    project_file_path: Path = project_dir / "streambuild_project.yml"
    project_file_path.parent.mkdir(parents=True, exist_ok=True)
    project_file_path.write_text("default_database: analytics\n", encoding="utf-8")
    return project_file_path


def write_macro_file(project_dir: Path, relative_path: str, contents: str) -> Path:
    macro_file_path: Path = project_dir / "macros" / relative_path
    macro_file_path.parent.mkdir(parents=True, exist_ok=True)
    macro_file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")
    return macro_file_path


def write_sql_file(project_dir: Path, relative_path: str, contents: str) -> Path:
    sql_file_path: Path = project_dir / relative_path
    sql_file_path.parent.mkdir(parents=True, exist_ok=True)
    sql_file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")
    return sql_file_path
