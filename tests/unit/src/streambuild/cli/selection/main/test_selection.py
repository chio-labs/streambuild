from __future__ import annotations

from dataclasses import replace

import pytest

from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.cli.selection.models import SelectionResolution
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.types import ReplayLineageMode
from tests.unit.src.streambuild.cli.selection.main._test_types import (
    CliSelectionLineageMismatchTestCase,
    CliSelectionResolutionErrorTestCase,
    CliSelectionResolutionTestCase,
)
from tests.unit.src.streambuild.cli.selection.main.helpers import (
    compile_selector_project_pipelines,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliSelectionResolutionTestCase(
            description="bare model selector includes downstream closure and upstream deps",
            selectors=("orders_clean",),
            expected_selected_model_names=("tbl__orders_clean",),
            expected_object_names=(
                "kafka__orders",
                "raw__orders",
                "mv__orders",
                "tbl__orders_clean",
                "mv__orders_clean",
                "tbl__orders_enriched",
                "mv__orders_enriched",
            ),
        ),
        CliSelectionResolutionTestCase(
            description="pipeline selector includes all authored models in one pipeline only",
            selectors=("pipeline:payments",),
            expected_selected_model_names=("tbl__payments_enriched",),
            expected_object_names=(
                "kafka__payments",
                "raw__payments",
                "mv__payments",
                "tbl__payments_enriched",
                "mv__payments_enriched",
            ),
        ),
        CliSelectionResolutionTestCase(
            description="multiple selectors union before closure expansion",
            selectors=("orders_clean", "pipeline:payments"),
            expected_selected_model_names=("tbl__orders_clean", "tbl__payments_enriched"),
            expected_object_names=(
                "kafka__orders",
                "raw__orders",
                "mv__orders",
                "tbl__orders_clean",
                "mv__orders_clean",
                "tbl__orders_enriched",
                "mv__orders_enriched",
                "kafka__payments",
                "raw__payments",
                "mv__payments",
                "tbl__payments_enriched",
                "mv__payments_enriched",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_selectors_when_resolving_then_it_returns_expected_filtered_desired_state(
    test_case: CliSelectionResolutionTestCase,
) -> None:
    compiled_pipelines: tuple[CompiledPipeline, ...] = compile_selector_project_pipelines()

    resolution: SelectionResolution = resolve_selection(
        compiled_pipelines=compiled_pipelines, selectors=test_case.selectors
    )

    assert tuple(sorted(key.name for key in resolution.selected_model_keys)) == tuple(
        sorted(test_case.expected_selected_model_names)
    )
    assert tuple(sorted(object_.name for object_ in resolution.desired_state.objects)) == tuple(
        sorted(test_case.expected_object_names)
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CliSelectionResolutionErrorTestCase(
            description="plus syntax is rejected clearly",
            selectors=("+orders_clean",),
            expected_error_fragment="\\+.*is not supported",
        ),
        CliSelectionResolutionErrorTestCase(
            description="unknown selector namespace is rejected clearly",
            selectors=("tag:finance",),
            expected_error_fragment="Unsupported selector namespace 'tag'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_selectors_when_resolving_then_it_raises_clear_error(
    test_case: CliSelectionResolutionErrorTestCase,
) -> None:
    compiled_pipelines: tuple[CompiledPipeline, ...] = compile_selector_project_pipelines()

    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        resolve_selection(compiled_pipelines=compiled_pipelines, selectors=test_case.selectors)


@pytest.mark.parametrize(
    "test_case",
    [
        CliSelectionLineageMismatchTestCase(
            description="replay lineage mismatch error names conflicting pipelines and modes",
            selectors=(),
            mutated_pipeline_name="payments",
            expected_error_fragment=(
                "Selected pipelines disagree on replay_lineage_mode: "
                "orders=offsets, payments=timestamp"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_selected_pipeline_modes_when_resolving_then_it_raises_contextual_error(
    test_case: CliSelectionLineageMismatchTestCase,
) -> None:
    compiled_pipelines: tuple[CompiledPipeline, ...] = compile_selector_project_pipelines()
    mutated_compiled_pipelines: tuple[CompiledPipeline, ...] = tuple(
        replace(
            compiled_pipeline,
            effective_replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
        )
        if compiled_pipeline.pipeline.name == test_case.mutated_pipeline_name
        else compiled_pipeline
        for compiled_pipeline in compiled_pipelines
    )

    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        resolve_selection(
            compiled_pipelines=mutated_compiled_pipelines, selectors=test_case.selectors
        )
