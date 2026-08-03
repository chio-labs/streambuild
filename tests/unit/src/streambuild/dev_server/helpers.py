from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
    write_project_configuration_and_source,
)

_ORDERS_CLEAN_MODEL: str = """
MODEL (
  description "Cleaned order rows.",
  order_by ["order_id", "_replay_partition", "_replay_offset"],
  columns (
    order_id (description "Primary order id", audits [not_null]),
  ),
);

SELECT
  CAST(order_id AS String) AS order_id,
  _replay_partition::Int64 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset
FROM __ref("orders")
"""

_NOT_NULL_GENERIC_AUDIT: str = """
AUDIT ();

SELECT @column
FROM __ref("@model")
WHERE @column IS NULL
"""


def write_dev_server_project(*, project_dir: Path) -> None:
    write_project_configuration_and_source(project_dir=project_dir)
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "orders_clean.sql",
        _ORDERS_CLEAN_MODEL,
    )
    write_pipeline_file(
        project_dir / "audits" / "generic" / "not_null.sql",
        _NOT_NULL_GENERIC_AUDIT,
    )


def build_compile_callable(*, project_dir: Path) -> Callable[[], CompileAnalysis]:
    def run_compile() -> CompileAnalysis:
        return analyze_project(
            pipelines_root=project_dir / "pipelines",
            loaded_project=load_project_input_for_path(path=project_dir),
            adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
        )

    return run_compile


def break_project_compile(*, project_dir: Path) -> None:
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "broken.sql",
        "SELECT 1 AS value",
    )


def build_test_client(*, project_dir: Path) -> TestClient:
    state: DevServerState = DevServerState(
        run_compile=build_compile_callable(project_dir=project_dir)
    )
    return TestClient(create_dev_app(state=state))


def named_payload_item(items: list, name: str) -> dict:
    by_name: dict = {item["name"]: item for item in items}
    return by_name[name]


def maybe_break_project_compile(*, project_dir: Path, break_compile: bool) -> None:
    writers: dict[bool, Callable[..., None]] = {
        True: break_project_compile,
        False: _skip_break,
    }
    writer: Callable[..., None] = writers[break_compile]
    writer(project_dir=project_dir)


def _skip_break(*, project_dir: Path) -> None:
    return None
