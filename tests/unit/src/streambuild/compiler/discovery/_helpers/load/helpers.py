from pathlib import Path
from textwrap import dedent


def write_pipeline_file(pipeline_file_path: Path, contents: str) -> None:
    pipeline_file_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline_file_path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")
