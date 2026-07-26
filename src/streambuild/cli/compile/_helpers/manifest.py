"""Manifest payload helpers for the compile command."""

from pathlib import Path

from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledManagedSource,
    CompiledPipeline,
)


def pipeline_manifest_entry(
    *,
    compiled_pipeline: CompiledPipeline,
    target_dir: Path,
) -> dict[str, object]:
    """Build one manifest payload entry for a compiled pipeline."""

    resolved_database: str = (
        compiled_pipeline.project.default_database
        if compiled_pipeline.project is not None
        and compiled_pipeline.project.default_database is not None
        else "default"
    )
    pipeline_target_dir: Path = target_dir / compiled_pipeline.pipeline.name
    return {
        "name": compiled_pipeline.pipeline.name,
        "file": str(compiled_pipeline.file_path),
        "source_name": compiled_pipeline.pipeline.source.name,
        "resolved_database": resolved_database,
        "replay_lineage_mode": str(compiled_pipeline.effective_replay_lineage_mode),
        "relations": compiled_pipeline.relation_names,
        "landing": _pipeline_landing_manifest_entry(compiled_pipeline),
        "models": {
            transform.transform.name: {
                "name": transform.transform.name,
                "source": transform.transform.source,
                "refs": list(transform.refs),
                "target_table_name": transform.target_table_name,
                "materialized_view_name": transform.materialized_view.name,
                "resolved_query_path": str(
                    pipeline_target_dir / "compile" / "models" / f"{transform.transform.name}.sql"
                ),
                "table_ddl_path": str(
                    pipeline_target_dir / "run" / "models" / f"{transform.transform.name}.table.sql"
                ),
                "mv_ddl_path": str(
                    pipeline_target_dir / "run" / "models" / f"{transform.transform.name}.mv.sql"
                ),
                "spec": {
                    "engine": transform.target_table.engine,
                    "order_by": list(transform.target_table.order_by),
                    "partition_by": transform.target_table.partition_by,
                    "ttl": transform.target_table.ttl,
                    "settings": transform.target_table.settings,
                    "columns": [
                        {"name": column.name, "type": column.type, "default": column.default}
                        for column in transform.target_table.columns
                    ],
                },
            }
            for transform in compiled_pipeline.transforms
        },
        "workflow": {
            "workflow_sql_path": str(pipeline_target_dir / "run" / "workflow" / "workflow.sql"),
            "workflow_json_path": str(pipeline_target_dir / "run" / "workflow" / "workflow.json"),
            "step_paths": [
                str(pipeline_target_dir / "run" / "workflow" / step_file)
                for step_file in workflow_step_files(compiled_pipeline)
            ],
        },
    }


def workflow_step_files(compiled_pipeline: CompiledPipeline) -> list[str]:
    """Return workflow step file names for one pipeline."""

    landing_files: list[str] = []
    if isinstance(compiled_pipeline.source, CompiledManagedSource):
        landing_files = ["01_kafka_table.sql", "02_raw_table.sql", "03_landing_mv.sql"]
    return [
        *landing_files,
        *[
            f"{index * 10:02d}_{transform.transform.name}.table.sql"
            for index, transform in enumerate(compiled_pipeline.transforms, start=1)
        ],
        *[
            f"{index * 10 + 1:02d}_{transform.transform.name}.mv.sql"
            for index, transform in enumerate(compiled_pipeline.transforms, start=1)
        ],
    ]


def _pipeline_landing_manifest_entry(compiled_pipeline: CompiledPipeline) -> dict[str, object]:
    if isinstance(compiled_pipeline.source, CompiledManagedSource):
        return {
            "kind": "kafka",
            "managed": True,
            "source_name": compiled_pipeline.pipeline.source.name,
            "kafka_table_name": compiled_pipeline.source.kafka_table.name,
            "raw_table_name": compiled_pipeline.source.raw_table.name,
            "landing_mv_name": compiled_pipeline.source.materialized_view.name,
        }
    external_source: CompiledExternalSource = compiled_pipeline.source
    return {
        "kind": str(external_source.source.kind),
        "managed": False,
        "source_name": external_source.source.name,
        "table_name": external_source.source.table_name,
        "replay_boundary": {
            "mode": str(external_source.source.replay_boundary.mode),
            "columns": {
                "_replay_partition": external_source.source.replay_boundary.columns.partition,
                "_replay_offset": external_source.source.replay_boundary.columns.offset,
                "_replay_timestamp": external_source.source.replay_boundary.columns.timestamp,
                "_replay_landed_at": external_source.source.replay_boundary.columns.landed_at,
                "_replay_cursor": external_source.source.replay_boundary.columns.cursor,
            },
        },
    }
