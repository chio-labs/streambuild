from pathlib import Path
from textwrap import dedent


def write_pipeline_file(pipeline_file_path: Path, contents: str) -> None:
    pipeline_file_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline_file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")


def write_registry_project(
    *, project_dir: Path, pipeline_config_contents: str, model_contents: str
) -> Path:
    pipeline_dir: Path = project_dir / "pipelines" / "orders"
    write_project_configuration_and_source(project_dir=project_dir)
    write_pipeline_file(pipeline_dir / "pipeline.toml", pipeline_config_contents)
    write_pipeline_file(
        pipeline_dir / "orders_enriched.sql",
        model_contents,
    )
    return pipeline_dir


def write_project_configuration_and_source(*, project_dir: Path) -> None:
    write_pipeline_file(
        project_dir / "streambuild_project.toml",
        """
        name = "test_project"
        default_target = "dev"

        [settings]
        virtual_environments = true

        [targets.dev]
        database = "analytics"
        """,
    )
    write_pipeline_file(
        project_dir / "sources" / "orders.yml",
        """
        sources:
          - name: orders
            kind: kafka
            broker_list: kafka:9092
            topic: source.orders
            replay_boundary:
              mode: offsets
        """,
    )
