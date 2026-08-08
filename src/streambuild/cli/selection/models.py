"""CLI selection models."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.compile.models import DesiredState, LogicalResourceKey, ObjectKey
from streambuild.compiler.discovery.types import ReplayLineageMode


@dataclass(frozen=True)
class SelectionResolution:
    desired_state: DesiredState
    selected_logical_model_keys: frozenset[LogicalResourceKey]
    selected_model_keys: frozenset[ObjectKey]
    replay_lineage_mode: ReplayLineageMode | None
    execution_logical_model_keys: frozenset[LogicalResourceKey] = frozenset()
