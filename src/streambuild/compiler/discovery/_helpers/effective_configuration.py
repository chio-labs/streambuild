"""Project and local configuration precedence resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from streambuild.compiler.discovery._helpers.interpolation import (
    interpolate_config_value,
    resolve_variable_values,
)
from streambuild.compiler.discovery.exceptions import ProjectConfigError
from streambuild.compiler.discovery.models import (
    AuditSchedulerConfig,
    AuthoredProjectConfig,
    EffectiveProjectConfiguration,
    LoadedProjectConfiguration,
    LocalProjectConfig,
    LocalProjectTarget,
    ProjectDefaults,
    ProjectNaming,
    ProjectSettings,
    ProjectTarget,
    RawConnectionConfig,
)


def resolve_effective_project_configuration(
    *,
    loaded: LoadedProjectConfiguration,
    selected_target: str | None,
    cli_variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> EffectiveProjectConfiguration:
    """Resolve one connection-lazy effective project configuration."""

    project: AuthoredProjectConfig = loaded.project
    local: LocalProjectConfig = loaded.local
    target_name: str = selected_target or local.target or project.default_target
    project_targets: dict[str, ProjectTarget] = dict(project.targets)
    local_targets: dict[str, LocalProjectTarget] = dict(local.targets)
    if target_name not in project_targets and target_name not in local_targets:
        raise ProjectConfigError(f"Unknown target '{target_name}'")
    project_target: ProjectTarget = project_targets.get(target_name, ProjectTarget())
    local_target: LocalProjectTarget = local_targets.get(target_name, LocalProjectTarget())
    merged_variables: dict[str, object] = {
        **dict(project.variables),
        **dict(project_target.variables),
        **dict(local_target.variables),
        **dict(local.variables),
        **dict(cli_variables),
    }
    variables: dict[str, object] = resolve_variable_values(
        values=merged_variables,
        environment=environment,
        field_path_prefix=str(loaded.project_source.file_path),
        defer_missing_environment=True,
    )
    raw_database: str | None = (
        local_target.database if local_target.database is not None else project_target.database
    )
    database: str | None = _optional_interpolated_string(
        value=raw_database,
        variables=variables,
        environment=environment,
        field_path=f"{loaded.project_source.file_path} targets.{target_name}.database",
    )
    return EffectiveProjectConfiguration(
        name=project.name,
        adapter=_interpolated_string(
            value=local.adapter or project.adapter,
            variables=variables,
            environment=environment,
            field_path=f"{loaded.project_source.file_path} adapter",
        ),
        target_name=target_name,
        settings=ProjectSettings(
            virtual_environments=_resolve_virtual_environments(
                loaded=loaded,
                variables=variables,
                environment=environment,
            )
        ),
        database=database,
        connection=RawConnectionConfig(
            values=tuple(
                sorted(
                    {
                        **dict(project.connection.values),
                        **dict(project_target.connection.values),
                        **dict(local_target.connection.values),
                        **dict(local.connection.values),
                    }.items()
                )
            )
        ),
        variables=tuple(sorted(variables.items())),
        defaults=_resolve_project_defaults(
            loaded=loaded,
            variables=variables,
            environment=environment,
        ),
        naming=_resolve_project_naming(
            loaded=loaded,
            variables=variables,
            environment=environment,
        ),
        audit_scheduler=AuditSchedulerConfig(
            enabled=(
                local_target.audit_scheduler.enabled
                if local_target.audit_scheduler.enabled is not None
                else (
                    project_target.audit_scheduler.enabled
                    if project_target.audit_scheduler.enabled is not None
                    else project.audit_scheduler.enabled
                )
            )
        ),
    )


def _resolve_virtual_environments(
    *,
    loaded: LoadedProjectConfiguration,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> bool:
    local_value: bool | str | None = loaded.local.settings.virtual_environments
    raw_value: bool | str = (
        local_value if local_value is not None else loaded.project.settings.virtual_environments
    )
    source_path: str = str(
        loaded.local_source.file_path
        if local_value is not None and loaded.local_source is not None
        else loaded.project_source.file_path
    )
    value: object = interpolate_config_value(
        value=raw_value,
        variables=variables,
        environment=environment,
        field_path=f"{source_path} settings.virtual_environments",
    )
    if not isinstance(value, bool):
        raise ProjectConfigError(
            f"{source_path} settings.virtual_environments must resolve to a boolean"
        )
    return value


def _resolve_project_defaults(
    *,
    loaded: LoadedProjectConfiguration,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> ProjectDefaults:
    defaults: ProjectDefaults = loaded.project.defaults
    return replace(
        defaults,
        managed_source_ttl=_optional_interpolated_string(
            value=defaults.managed_source_ttl,
            variables=variables,
            environment=environment,
            field_path=f"{loaded.project_source.file_path} defaults.managed_source_ttl",
        ),
        model_ttl=_optional_interpolated_string(
            value=defaults.model_ttl,
            variables=variables,
            environment=environment,
            field_path=f"{loaded.project_source.file_path} defaults.model_ttl",
        ),
        kafka_broker_list=_optional_interpolated_string(
            value=defaults.kafka_broker_list,
            variables=variables,
            environment=environment,
            field_path=f"{loaded.project_source.file_path} defaults.kafka_broker_list",
        ),
    )


def _resolve_project_naming(
    *,
    loaded: LoadedProjectConfiguration,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> ProjectNaming:
    naming: ProjectNaming = loaded.project.naming
    return ProjectNaming(
        table_prefix=_interpolated_string(
            value=naming.table_prefix,
            variables=variables,
            environment=environment,
            field_path=f"{loaded.project_source.file_path} naming.table_prefix",
        ),
        view_prefix=_interpolated_string(
            value=naming.view_prefix,
            variables=variables,
            environment=environment,
            field_path=f"{loaded.project_source.file_path} naming.view_prefix",
        ),
    )


def _optional_interpolated_string(
    *,
    value: str | None,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    field_path: str,
) -> str | None:
    if value is None:
        return None
    return _interpolated_string(
        value=value,
        variables=variables,
        environment=environment,
        field_path=field_path,
    )


def _interpolated_string(
    *,
    value: str,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    field_path: str,
) -> str:
    interpolated: object = interpolate_config_value(
        value=value,
        variables=variables,
        environment=environment,
        field_path=field_path,
    )
    if not isinstance(interpolated, str):
        raise ProjectConfigError(f"{field_path} must resolve to a string")
    return interpolated
