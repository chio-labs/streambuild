from __future__ import annotations

from streambuild.cli.selection._helpers.selection import (
    expand_included_keys,
    filter_desired_state,
    resolve_replay_lineage_mode,
    resolve_selected_model_keys,
)
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import (
    CompiledPipeline,
    DesiredState,
    ObjectKey,
)
from streambuild.compiler.desired_state.main.build_desired_state import build_desired_state


def resolve_selection(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    selectors: tuple[str, ...],
) -> SelectionResolution:
    full_desired_state: DesiredState = build_desired_state(compiled_pipelines)
    if not selectors:
        return SelectionResolution(
            desired_state=full_desired_state,
            selected_model_keys=frozenset(),
            replay_lineage_mode=resolve_replay_lineage_mode(
                compiled_pipelines=compiled_pipelines,
                selected_model_keys=frozenset(),
            ),
        )

    selected_model_keys: frozenset[ObjectKey] = resolve_selected_model_keys(
        compiled_pipelines=compiled_pipelines,
        selectors=selectors,
    )
    included_keys: frozenset[ObjectKey] = expand_included_keys(
        compiled_pipelines=compiled_pipelines,
        desired_state=full_desired_state,
        selected_model_keys=selected_model_keys,
    )
    return SelectionResolution(
        desired_state=filter_desired_state(
            desired_state=full_desired_state, included_keys=included_keys
        ),
        selected_model_keys=selected_model_keys,
        replay_lineage_mode=resolve_replay_lineage_mode(
            compiled_pipelines=compiled_pipelines,
            selected_model_keys=selected_model_keys,
        ),
    )
