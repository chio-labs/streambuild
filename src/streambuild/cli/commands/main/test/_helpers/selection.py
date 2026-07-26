"""Selector and path filtering helpers for SQL-native tests."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from streambuild.cli.commands.main.shared.exceptions import CliUserError
from streambuild.compiler.compile.models import CompiledPipeline, CompiledTransformStep, ParsedRef
from streambuild.compiler.shared.models import LoadedSqlTest


def select_loaded_sql_tests(
    *,
    loaded_tests: tuple[LoadedSqlTest, ...],
    compiled_pipelines: tuple[CompiledPipeline, ...],
    selectors: tuple[str, ...],
    paths: tuple[Path, ...],
    project_dir: Path,
) -> tuple[LoadedSqlTest, ...]:
    """Filter discovered SQL tests by target selectors and explicit paths."""

    if not selectors and not paths:
        return loaded_tests
    selected_paths: set[Path] = _resolve_selected_paths(paths=paths, project_dir=project_dir)
    selected_target_names: frozenset[str] = _resolve_selected_target_names(
        compiled_pipelines=compiled_pipelines,
        selectors=selectors,
    )
    selected_tests: tuple[LoadedSqlTest, ...] = tuple(
        loaded_test
        for loaded_test in loaded_tests
        if loaded_test.file_path.resolve() in selected_paths
        or any(
            expected_target.name.removeprefix("__expected__") in selected_target_names
            for expected_target in loaded_test.expected_targets
        )
    )
    if selected_tests:
        return selected_tests
    raise CliUserError("No SQL tests matched the requested selectors or paths.")


def _resolve_selected_paths(*, paths: tuple[Path, ...], project_dir: Path) -> set[Path]:
    resolved_paths: set[Path] = set()
    raw_path: Path
    for raw_path in paths:
        resolved_path: Path = raw_path if raw_path.is_absolute() else (project_dir / raw_path)
        if resolved_path.is_dir():
            resolved_paths.update(path.resolve() for path in resolved_path.rglob("*.sql"))
            continue
        resolved_paths.add(resolved_path.resolve())
    return resolved_paths


def _resolve_selected_target_names(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    selectors: tuple[str, ...],
) -> frozenset[str]:
    if not selectors:
        return frozenset()
    pipeline_model_names: dict[str, tuple[str, ...]] = {
        compiled_pipeline.pipeline.name: tuple(
            compiled_transform.transform.name for compiled_transform in compiled_pipeline.transforms
        )
        for compiled_pipeline in compiled_pipelines
    }
    upstream_names_by_model, downstream_names_by_model = _build_model_graph(compiled_pipelines)
    known_model_names: frozenset[str] = frozenset(downstream_names_by_model)
    selected_target_names: set[str] = set()
    raw_selector: str
    for raw_selector in selectors:
        include_upstream: bool = raw_selector.startswith("+")
        include_downstream: bool = raw_selector.endswith("+")
        selector: str = raw_selector.removeprefix("+").removesuffix("+")
        if not selector or "+" in selector:
            raise CliUserError(
                f"Unsupported test selector syntax '{raw_selector}'. Use bare model names, "
                "pipeline:<name>, or optional leading/trailing '+'."
            )
        base_target_names: tuple[str, ...] = _resolve_selector_target_names(
            selector=selector,
            pipeline_model_names=pipeline_model_names,
            known_model_names=known_model_names,
        )
        selected_target_names.update(base_target_names)
        if include_upstream:
            base_target_name: str
            for base_target_name in base_target_names:
                selected_target_names.update(
                    _expand_graph_neighbors(
                        start_name=base_target_name, neighbors_by_name=upstream_names_by_model
                    )
                )
        if include_downstream:
            base_target_name: str
            for base_target_name in base_target_names:
                selected_target_names.update(
                    _expand_graph_neighbors(
                        start_name=base_target_name, neighbors_by_name=downstream_names_by_model
                    )
                )
    return frozenset(selected_target_names)


def _resolve_selector_target_names(
    *,
    selector: str,
    pipeline_model_names: dict[str, tuple[str, ...]],
    known_model_names: frozenset[str],
) -> tuple[str, ...]:
    if ":" not in selector:
        if selector not in known_model_names:
            raise CliUserError(f"Unknown SQL test selector model '{selector}'")
        return (selector,)
    selector_kind: str
    selector_value: str
    selector_kind, selector_value = selector.split(":", 1)
    if selector_kind != "pipeline":
        raise CliUserError(f"Unsupported test selector namespace '{selector_kind}' in '{selector}'")
    pipeline_targets: tuple[str, ...] | None = pipeline_model_names.get(selector_value)
    if pipeline_targets is None:
        raise CliUserError(f"Unknown SQL test selector pipeline '{selector_value}'")
    if not pipeline_targets:
        raise CliUserError(
            f"SQL test selector pipeline '{selector_value}' does not define any models"
        )
    return pipeline_targets


def _build_model_graph(
    compiled_pipelines: tuple[CompiledPipeline, ...],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    downstream_names_by_model: dict[str, set[str]] = defaultdict(set)
    upstream_names_by_model: dict[str, set[str]] = defaultdict(set)
    known_model_names: set[str] = {
        compiled_transform.transform.name
        for compiled_pipeline in compiled_pipelines
        for compiled_transform in compiled_pipeline.transforms
    }
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        compiled_transform: CompiledTransformStep
        for compiled_transform in compiled_pipeline.transforms:
            model_name: str = compiled_transform.transform.name
            downstream_names_by_model.setdefault(model_name, set())
            upstream_names_by_model.setdefault(model_name, set())
            parsed_ref: ParsedRef
            for parsed_ref in compiled_transform.parsed_refs:
                if parsed_ref.name not in known_model_names:
                    continue
                upstream_names_by_model[model_name].add(parsed_ref.name)
                downstream_names_by_model[parsed_ref.name].add(model_name)
    return (
        {name: tuple(sorted(neighbors)) for name, neighbors in upstream_names_by_model.items()},
        {name: tuple(sorted(neighbors)) for name, neighbors in downstream_names_by_model.items()},
    )


def _expand_graph_neighbors(
    *,
    start_name: str,
    neighbors_by_name: dict[str, tuple[str, ...]],
) -> frozenset[str]:
    visited_names: set[str] = set()
    stack: list[str] = [start_name]
    while stack:
        current_name: str = stack.pop()
        neighbor_name: str
        for neighbor_name in neighbors_by_name.get(current_name, ()):
            if neighbor_name in visited_names:
                continue
            visited_names.add(neighbor_name)
            stack.append(neighbor_name)
    return frozenset(visited_names)
