from pathlib import Path

from streambuild.clickhouse.render.main._render_desired_state_ddl import render_desired_state_ddl
from streambuild.clickhouse.render.models import RenderedClickHouseDdl
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.desired_state.main import build_desired_state
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.shared.models import LoadedPipeline, ObjectKey

EXAMPLE_PIPELINE_FILE_PATH: Path = Path(
    "tests/fixtures/basic_project/pipelines/orders/pipeline.yml"
)


def build_example_desired_state() -> DesiredState:
    loaded_pipeline: LoadedPipeline = load_pipeline_file(EXAMPLE_PIPELINE_FILE_PATH)
    return build_desired_state((compile_pipeline(loaded_pipeline),))


def render_example_desired_state(
    database: str,
) -> tuple[RenderedClickHouseDdl, ...]:
    desired_state: DesiredState = build_example_desired_state()
    return render_desired_state_ddl(
        desired_state=desired_state,
        database=database,
    )


def rendered_keys(
    rendered_objects: tuple[RenderedClickHouseDdl, ...],
) -> tuple[tuple[str | None, str, str], ...]:
    return tuple(_key_parts(rendered_object.key) for rendered_object in rendered_objects)


def _key_parts(key: ObjectKey) -> tuple[str | None, str, str]:
    return (key.database, key.object_type, key.name)
