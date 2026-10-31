"""Write the generated chain project that exercises a deeper model graph."""

from pathlib import Path

_SOURCE_YAML: str = (
    "sources:\n"
    "  - name: chain_source\n"
    "    kind: kafka\n"
    "    broker_list: kafka:9092\n"
    "    topic: source.chain\n"
    "    replay_boundary:\n"
    "      mode: offsets\n"
)


def write_generated_chain_project(*, project_dir: Path, model_count: int) -> None:
    pipeline_dir: Path = project_dir / "pipelines" / "pl__chain"
    pipeline_dir.mkdir(parents=True)
    (project_dir / "sqltide_project.toml").write_text(
        'name = "generated_chain"\ndefault_target = "test"\n\n'
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    (project_dir / "sources").mkdir()
    (project_dir / "sources" / "chain_source.yml").write_text(_SOURCE_YAML, encoding="utf-8")
    upstream_names: tuple[str, ...] = (
        "chain_source",
        *(f"model_{index:03d}" for index in range(model_count - 1)),
    )
    for index, upstream_name in enumerate(upstream_names):
        (pipeline_dir / f"model_{index:03d}.sql").write_text(
            _model_sql(index=index, upstream_name=upstream_name), encoding="utf-8"
        )


def _model_sql(*, index: int, upstream_name: str) -> str:
    reference: str = f'__source("{upstream_name}")' if index == 0 else f'__ref("{upstream_name}")'
    value_expression: str = (
        "JSONExtractString(kafka_value, 'order_id')" if index == 0 else "order_id"
    )
    return (
        "MODEL (\n"
        '  engine "MergeTree()",\n'
        '  order_by ["order_id", "_replay_partition", "_replay_offset"],\n'
        f'  description "Generated chain step {index}.",\n'
        ");\n\n"
        "SELECT\n"
        f"  CAST({value_expression} AS String) AS order_id,\n"
        "  _replay_partition::Int32 AS _replay_partition,\n"
        "  _replay_offset::Int64 AS _replay_offset,\n"
        "  _replay_timestamp::DateTime64(3) AS _replay_timestamp\n"
        f"FROM {reference}\n"
    )
