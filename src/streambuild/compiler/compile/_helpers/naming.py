"""Compile-local physical naming and authored model relation rules."""

import re

from streambuild.compiler.compile.constants import (
    KAFKA_TABLE_NAME_PREFIX,
    MATERIALIZED_VIEW_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import CompiledProject
from streambuild.compiler.discovery.constants import DEFAULT_TABLE_PREFIX, DEFAULT_VIEW_PREFIX
from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    Pipeline,
    Project,
    TransformStep,
    ViewStep,
)
from streambuild.compiler.discovery.types import ModelKind

_UNQUALIFIED_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEPLOYMENT_SUFFIX_PATTERN: re.Pattern[str] = re.compile(
    r"__(?:\d{8}T\d{6}Z_[0-9a-f]{6}|reconcile_\d{8}T\d{6}Z)$"
)
_RESERVED_MODEL_RELATION_PREFIXES: tuple[str, ...] = (
    KAFKA_TABLE_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
    MATERIALIZED_VIEW_NAME_PREFIX,
)


def kafka_table_name(logical_name: str) -> str:
    return f"{KAFKA_TABLE_NAME_PREFIX}{logical_name}"


def raw_table_name(logical_name: str) -> str:
    return f"{RAW_TABLE_NAME_PREFIX}{logical_name}"


def landing_mv_name(logical_name: str) -> str:
    return f"{MATERIALIZED_VIEW_NAME_PREFIX}{logical_name}"


def transform_mv_name(logical_name: str) -> str:
    return f"{MATERIALIZED_VIEW_NAME_PREFIX}{logical_name}"


def resolve_model_relation_name(
    *, model: TransformStep | ViewStep, pipeline: Pipeline, project: Project | None
) -> str:
    """Resolve and validate one model relation name using authored precedence."""

    kind: ModelKind = ModelKind.TABLE if isinstance(model, TransformStep) else ModelKind.VIEW
    exact_name: str | None = model.relation_name
    if exact_name is not None:
        relation_name: str = exact_name
    else:
        pipeline_prefix: str | None = (
            pipeline.naming.table_prefix if kind == ModelKind.TABLE else pipeline.naming.view_prefix
        )
        project_prefix: str | None = None
        if project is not None:
            project_prefix = (
                project.naming.table_prefix
                if kind == ModelKind.TABLE
                else project.naming.view_prefix
            )
        built_in_prefix: str = (
            DEFAULT_TABLE_PREFIX if kind == ModelKind.TABLE else DEFAULT_VIEW_PREFIX
        )
        prefix: str = (
            pipeline_prefix
            if pipeline_prefix is not None
            else project_prefix
            if project_prefix is not None
            else built_in_prefix
        )
        relation_name = f"{prefix}{model.name}"
    _validate_model_relation_name(logical_name=model.name, relation_name=relation_name)
    return relation_name


def validate_compiled_project_relation_names(*, project: CompiledProject) -> None:
    """Reject project-wide physical relation collisions before graph or realization work."""

    owner_by_relation_name: dict[str, str] = {}
    adopted_owner_by_relation_name: dict[str, str] = {}
    for source in project.sources:
        authored_source: KafkaLandingStep | ExternalTableSourceStep = source.source
        if isinstance(authored_source, ExternalTableSourceStep):
            adopted_owner_by_relation_name.setdefault(
                authored_source.table_name,
                f"adopted source '{source.key.name}'",
            )
            continue
        for relation_name, role in (
            (kafka_table_name(source.key.name), "Kafka table"),
            (raw_table_name(source.key.name), "raw table"),
            (landing_mv_name(source.key.name), "landing materialized view"),
        ):
            owner_by_relation_name = _claim_relation_name(
                relation_name=relation_name,
                owner=f"generated {role} for source '{source.key.name}'",
                owner_by_relation_name=owner_by_relation_name,
            )
    for model in project.models:
        owner_by_relation_name = _claim_relation_name(
            relation_name=model.relation_name,
            owner=f"model '{model.key.name}'",
            owner_by_relation_name=owner_by_relation_name,
        )
        if model.kind == ModelKind.TABLE:
            owner_by_relation_name = _claim_relation_name(
                relation_name=transform_mv_name(model.key.name),
                owner=f"generated materialized view for model '{model.key.name}'",
                owner_by_relation_name=owner_by_relation_name,
            )
    relation_name: str
    adopted_owner: str
    for relation_name, adopted_owner in adopted_owner_by_relation_name.items():
        owner_by_relation_name = _claim_relation_name(
            relation_name=relation_name,
            owner=adopted_owner,
            owner_by_relation_name=owner_by_relation_name,
        )


def _validate_model_relation_name(*, logical_name: str, relation_name: str) -> None:
    if not relation_name or _UNQUALIFIED_IDENTIFIER_PATTERN.fullmatch(relation_name) is None:
        raise PipelineCompileError(
            f"Model '{logical_name}' resolves to invalid relation name '{relation_name}'; "
            "expected a non-empty unqualified identifier"
        )
    if relation_name.startswith(_RESERVED_MODEL_RELATION_PREFIXES):
        raise PipelineCompileError(
            f"Model '{logical_name}' relation name '{relation_name}' uses reserved prefix; "
            "kafka__, raw__, and mv__ are framework-owned"
        )
    if _DEPLOYMENT_SUFFIX_PATTERN.search(relation_name) is not None:
        raise PipelineCompileError(
            f"Model '{logical_name}' relation name '{relation_name}' looks like a fixed "
            "deployment-suffixed physical name"
        )


def _claim_relation_name(
    *, relation_name: str, owner: str, owner_by_relation_name: dict[str, str]
) -> dict[str, str]:
    existing_owner: str | None = owner_by_relation_name.get(relation_name)
    if existing_owner is not None:
        raise PipelineCompileError(
            f"Relation name '{relation_name}' is used by both {existing_owner} and {owner}"
        )
    owner_by_relation_name[relation_name] = owner
    return owner_by_relation_name
