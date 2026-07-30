"""Load project config with retained source for one connection-free invocation."""

from collections.abc import Mapping
from pathlib import Path

from streambuild.compiler.discovery._helpers.configuration import (
    find_project_configuration_dir,
    load_project_configuration,
)
from streambuild.compiler.discovery._helpers.effective_configuration import (
    resolve_effective_project_configuration,
)
from streambuild.compiler.discovery._helpers.source_registry import discover_source_registry
from streambuild.compiler.discovery.models import (
    EffectiveProjectConfiguration,
    LoadedProject,
    LoadedProjectConfiguration,
    Project,
)


def load_project_input_for_path(
    *,
    path: Path,
    selected_target: str | None = None,
    cli_variables: Mapping[str, object] | None = None,
    environment: Mapping[str, str] | None = None,
) -> LoadedProject | None:
    """Load the nearest project config and retain the exact authored contents."""

    project_dir: Path | None = find_project_configuration_dir(path)
    if project_dir is None:
        return None
    configuration: LoadedProjectConfiguration = load_project_configuration(project_dir=project_dir)
    effective: EffectiveProjectConfiguration = resolve_effective_project_configuration(
        loaded=configuration,
        selected_target=selected_target,
        cli_variables={} if cli_variables is None else cli_variables,
        environment={} if environment is None else environment,
    )
    project: Project = Project(
        replay_on_change=effective.defaults.replay_on_change,
        default_database=effective.database,
        adapter=effective.adapter,
        bounded_replay_fallback=effective.defaults.bounded_replay_fallback,
    )
    return LoadedProject(
        project=project,
        source_file=configuration.project_source,
        configuration=configuration,
        effective_configuration=effective,
        source_files=discover_source_registry(
            project_dir=project_dir,
            variables=dict(effective.variables),
            environment={} if environment is None else environment,
            default_managed_source_ttl=effective.defaults.managed_source_ttl,
        ),
    )
