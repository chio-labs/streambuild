from pathlib import Path
from textwrap import dedent

from streambuild.compiler.discovery.models import DiscoveredProjectFile
from streambuild.compiler.macros.main._build_macro_context import build_macro_context
from streambuild.compiler.macros.main._expand_macro_calls import expand_macro_calls
from streambuild.compiler.macros.main._load_macro_registry import load_macro_registry
from streambuild.compiler.macros.models import MacroContext, MacroRegistry


def build_test_macro_runtime(project_dir: Path) -> tuple[MacroRegistry, MacroContext]:
    macro_files: tuple[DiscoveredProjectFile, ...] = tuple(
        DiscoveredProjectFile(
            file_path=macro_path,
            relative_path=macro_path.relative_to(project_dir),
            contents=macro_path.read_text(encoding="utf-8"),
        )
        for macro_path in sorted((project_dir / "macros").rglob("*.py"))
    )
    registry: MacroRegistry = load_macro_registry(macro_files=macro_files)
    context: MacroContext = build_macro_context(
        adapter_name="clickhouse",
        dialect="clickhouse",
        target_name="dev",
        database="analytics",
        schema=None,
        virtual_environments=False,
        variables={},
    )
    return registry, context


def expand_project_sql_macros(*, project_dir: Path, sql: str, file_path: Path) -> str:
    registry: MacroRegistry
    context: MacroContext
    registry, context = build_test_macro_runtime(project_dir)
    return expand_macro_calls(
        sql=sql,
        file_path=file_path,
        registry=registry,
        context=context,
    )


def write_project_file(project_dir: Path) -> Path:
    project_file_path: Path = project_dir / "streambuild_project.toml"
    project_file_path.parent.mkdir(parents=True, exist_ok=True)
    project_file_path.write_text(
        'name = "test_project"\ndefault_target = "dev"\n\n[targets.dev]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
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
