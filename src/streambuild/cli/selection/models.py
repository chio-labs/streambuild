"""CLI selection models."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.discovery.types import ReplayLineageMode


@dataclass(frozen=True)
class SelectionResolution:
    desired_state: DesiredState
    selected_model_keys: frozenset[ObjectKey]
    replay_lineage_mode: ReplayLineageMode
