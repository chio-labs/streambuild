from pathlib import Path

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis


def analyze_orders_demo() -> CompileAnalysis:
    project_dir: Path = Path("examples/orders_demo")
    loaded_project: LoadedProject | None = load_project_input_for_path(path=project_dir)
    return analyze_project(
        pipelines_root=project_dir / "pipelines",
        loaded_project=loaded_project,
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )
