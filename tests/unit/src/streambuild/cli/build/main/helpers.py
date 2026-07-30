from pathlib import Path

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.build.main._run_build import run_build
from streambuild.cli.build.models import BuildCommandOptions
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.planner.models import DirectWarehouseSnapshot
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.compiler.planner.helpers import build_settled_direct_snapshot


def run_scope_project_build(*, project_root: Path, json_output: bool, auto_approve: bool) -> int:
    """Run `stb build` against the scope project with a settled fake warehouse."""

    snapshot: DirectWarehouseSnapshot = build_settled_direct_snapshot()
    return run_build(
        options=BuildCommandOptions(
            pipelines_root=project_root / "pipelines",
            database=None,
            metadata_database=None,
            selectors=(),
            json_output=json_output,
            verbose=False,
            auto_approve=auto_approve,
        ),
        client=RecordingAdapterConnection(
            relations=snapshot.catalog.relations,
            ownership_records=snapshot.ownership_records,
        ),
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )
