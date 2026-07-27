import time
from pathlib import Path

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.pipeline.main.analyze_project import analyze_project


def run_compile_benchmark(*, project_dir: Path, model_count: int) -> float:
    write_compile_benchmark_project(project_dir=project_dir, model_count=model_count)
    start: float = time.perf_counter()
    _ = analyze_project(
        pipelines_root=project_dir / "pipelines",
        loaded_project=load_project_input_for_path(path=project_dir),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )
    return time.perf_counter() - start


def write_compile_benchmark_project(*, project_dir: Path, model_count: int) -> None:
    pipeline_dir: Path = project_dir / "pipelines" / "performance"
    pipeline_dir.mkdir(parents=True)
    (project_dir / "streambuild_project.toml").write_text(
        'name = "benchmark_project"\ndefault_target = "test"\n\n'
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    source_dir: Path = project_dir / "sources"
    source_dir.mkdir()
    (source_dir / "benchmark_source.yml").write_text(
        "sources:\n"
        "  - name: benchmark_source\n"
        "    kind: kafka\n"
        "    broker_list: kafka:9092\n"
        "    topic: source.benchmark\n"
        "    replay_boundary:\n"
        "      mode: offsets\n",
        encoding="utf-8",
    )
    (pipeline_dir / "pipeline.yml").write_text(
        "source: benchmark_source\n",
        encoding="utf-8",
    )
    (pipeline_dir / "model_00000.sql").write_text(
        _model_sql(upstream_name="benchmark_source"),
        encoding="utf-8",
    )
    index: int
    for index in range(1, model_count):
        (pipeline_dir / f"model_{index:05d}.sql").write_text(
            _model_sql(upstream_name=f"model_{index - 1:05d}"),
            encoding="utf-8",
        )


def _model_sql(*, upstream_name: str) -> str:
    return (
        'MODEL (\n  engine: "MergeTree()",\n  order_by: ["order_id"],\n);\n\n'
        "WITH base AS (\n"
        "  SELECT CAST(order_id AS UInt64) AS order_id\n"
        f'  FROM __ref("{upstream_name}")\n'
        ")\n"
        "SELECT CAST(order_id AS UInt64) AS order_id FROM base\n"
    )
