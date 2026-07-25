from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoadPipelineFileTestCase:
    description: str
    pipeline_file_path: Path
    expected_pipeline_name: str
    expected_source_name: str


@dataclass(frozen=True)
class DiscoverPipelinesTestCase:
    description: str
    pipelines_root: Path
    expected_pipeline_names: list[str]


@dataclass(frozen=True)
class DiscoverPipelinesErrorTestCase:
    description: str
    pipeline_files: dict[str, str]
    expected_error_type: type[Exception]
    expected_error_fragment: str
