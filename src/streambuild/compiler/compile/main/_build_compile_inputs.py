"""Apache-2.0: SQLBuild compiler/compile/main/_build_compile_inputs.py@7e3b2f854f05."""

from pathlib import Path

from streambuild.compiler.audit_discovery.main._discover_sql_audits import discover_sql_audits
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import (
    CompileProjectInputs,
    CompilerAdapterProfile,
    CompilerTargetMetadata,
)
from streambuild.compiler.discovery.main._load_discovered_pipelines import (
    load_discovered_pipelines,
)
from streambuild.compiler.discovery.main._source_registry_by_name import source_registry_by_name
from streambuild.compiler.discovery.main._validate_attached_project_inputs import (
    validate_attached_project_inputs,
)
from streambuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    EffectiveProjectConfiguration,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    Project,
)
from streambuild.compiler.macros.main._build_macro_context import build_macro_context
from streambuild.compiler.macros.main._load_macro_registry import load_macro_registry
from streambuild.compiler.macros.models import MacroContext, MacroRegistry
from streambuild.compiler.test_discovery.main._discover_sql_tests import discover_sql_tests
from streambuild.compiler.test_discovery.models import LoadedSqlTest


def build_compile_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter_profile: CompilerAdapterProfile,
) -> CompileProjectInputs:
    """Attach resolved target metadata and every discovered resource to one snapshot."""

    project: Project | None = (
        None
        if discovered_inputs.loaded_project is None
        else discovered_inputs.loaded_project.project
    )
    effective_target: CompilerTargetMetadata = CompilerTargetMetadata(
        default_database=(
            project.default_database
            if project is not None and project.default_database is not None
            else adapter_profile.target_metadata.default_database
        ),
        default_schema=adapter_profile.target_metadata.default_schema,
    )
    effective_configuration: EffectiveProjectConfiguration | None = (
        None
        if discovered_inputs.loaded_project is None
        else discovered_inputs.loaded_project.effective_configuration
    )
    variables: tuple[tuple[str, object], ...] = (
        () if effective_configuration is None else effective_configuration.variables
    )
    virtual_environments: bool = (
        False
        if effective_configuration is None
        else effective_configuration.settings.virtual_environments
    )
    macro_registry: MacroRegistry = load_macro_registry(macro_files=discovered_inputs.macro_files)
    macro_context: MacroContext = build_macro_context(
        adapter_name=adapter_profile.identity.name,
        dialect=adapter_profile.sql_analysis_dialect,
        target_name=(
            None if effective_configuration is None else effective_configuration.target_name
        ),
        database=effective_target.default_database,
        schema=effective_target.default_schema,
        virtual_environments=virtual_environments,
        variables=dict(variables),
    )
    sources_by_name: dict[str, KafkaLandingStep | ExternalTableSourceStep] = (
        source_registry_by_name(discovered_inputs.source_files)
    )
    pipelines: tuple[LoadedPipeline, ...] = load_discovered_pipelines(
        pipeline_directories=discovered_inputs.pipeline_directories,
        model_files=discovered_inputs.model_files,
        macro_registry=macro_registry,
        macro_context=macro_context,
        sources_by_name=sources_by_name,
        project=project,
    )
    contents_by_path: dict[Path, str] = {
        source_file.file_path: source_file.contents
        for source_file in (
            *discovered_inputs.test_files,
            *discovered_inputs.audit_files,
            *discovered_inputs.audit_schema_files,
        )
    }
    tests: tuple[LoadedSqlTest, ...] = tuple(
        discover_sql_tests(
            root=discovered_inputs.project_dir / "tests",
            contents_by_path=contents_by_path,
            macro_registry=macro_registry,
            macro_context=macro_context,
        )
    )
    audits: tuple[LoadedSqlAudit, ...] = tuple(
        discover_sql_audits(
            root=discovered_inputs.project_dir / "audits",
            contents_by_path=contents_by_path,
            macro_registry=macro_registry,
            macro_context=macro_context,
        )
    )
    validate_attached_project_inputs(
        source_files=discovered_inputs.source_files,
        loaded_project=discovered_inputs.loaded_project,
        loaded_pipelines=pipelines,
        loaded_tests=tests,
        loaded_audits=audits,
    )
    return CompileProjectInputs(
        discovered_inputs=discovered_inputs,
        adapter_profile=adapter_profile,
        effective_target=effective_target,
        variables=variables,
        macro_registry=macro_registry,
        macro_context=macro_context,
        pipelines=pipelines,
        tests=tests,
        audits=audits,
        sources=tuple(sources_by_name[name] for name in sorted(sources_by_name)),
        virtual_environments=virtual_environments,
    )
