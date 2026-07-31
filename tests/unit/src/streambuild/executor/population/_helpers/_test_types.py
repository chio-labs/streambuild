from collections.abc import Callable
from dataclasses import dataclass

from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.types import ReplayLineageMode


@dataclass(frozen=True)
class AdoptedFanInReplayTestCase:
    description: str
    compiled_pipeline_builder: Callable[[], CompiledPipeline]
    replay_lineage_mode: ReplayLineageMode
    physical_suffix: str
    watermark_column_names: tuple[str, ...]
    watermark_rows: tuple[tuple[object, ...], ...]
    expected_query_fragments: tuple[str, ...]
    expected_boundary_key: str
    expected_cutoff_value: str
    expected_partition_value: str | None
    expected_anchor_suffix: str
    expected_written_rows: int | None


@dataclass(frozen=True)
class WatermarkTraversalErrorTestCase:
    description: str
    parent_name: str
    expected_error_fragment: str
