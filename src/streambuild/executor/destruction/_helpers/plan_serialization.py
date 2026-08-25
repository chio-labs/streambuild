"""Strict, versioned serialization for durable destruction plans."""

from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError

from streambuild.executor.destruction.constants import DESTRUCTION_PLAN_PAYLOAD_VERSION
from streambuild.executor.destruction.exceptions import DestructionPlanCorruptError
from streambuild.executor.destruction.models import DestructionPlan, DestructionRelationEvidence
from streambuild.executor.destruction.types import (
    DestructionOperation,
    DestructionOwnership,
    DestructionRelationKind,
)


class _SerializedRelation(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    database: str
    name: str
    kind: DestructionRelationKind
    exists: bool
    total_bytes: int | None
    active_parts: int | None
    catalog_fingerprint: str | None
    logical_names: tuple[str, ...]
    pipeline_names: tuple[str, ...]
    ownership: tuple[DestructionOwnership, ...]
    dependency_relation_names: tuple[str, ...]


class _SerializedPlan(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    plan_id: str
    operation: DestructionOperation
    target: str
    database: str
    metadata_database: str
    requested_pipeline_names: tuple[str, ...]
    included_dependent_pipeline_names: tuple[str, ...]
    affected_pipeline_names: tuple[str, ...]
    affected_model_names: tuple[str, ...]
    affected_source_names: tuple[str, ...]
    relations: tuple[_SerializedRelation, ...]
    challenges: tuple[str, ...]
    preserves_sources: bool
    preserves_replay_data: bool
    manifest_fingerprint: str
    plan_fingerprint: str
    created_at: datetime
    expires_at: datetime
    relation_drop_size_limit: int | None = None
    relation_drop_size_server_limit: int | None = None
    relation_drop_size_override: int | None = None
    relation_drop_size_policy_observed: bool = False


class _SerializedEnvelope(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    version: int
    plan: _SerializedPlan


def serialize_destruction_plan(plan: DestructionPlan) -> str:
    """Serialize every immutable plan field into the current strict envelope."""

    envelope: _SerializedEnvelope = _SerializedEnvelope(
        version=DESTRUCTION_PLAN_PAYLOAD_VERSION,
        plan=_SerializedPlan.model_validate(plan, from_attributes=True),
    )
    return envelope.model_dump_json()


def deserialize_destruction_plan(payload_json: str) -> DestructionPlan:
    """Load a complete plan, rejecting unknown versions, fields, and invalid values."""

    try:
        envelope: _SerializedEnvelope = _SerializedEnvelope.model_validate_json(payload_json)
        if envelope.version != DESTRUCTION_PLAN_PAYLOAD_VERSION:
            raise DestructionPlanCorruptError(
                f"unsupported payload version {envelope.version}; "
                f"expected {DESTRUCTION_PLAN_PAYLOAD_VERSION}"
            )
        serialized: _SerializedPlan = envelope.plan
        created_at: datetime = _aware_utc(value=serialized.created_at, field="created_at")
        expires_at: datetime = _aware_utc(value=serialized.expires_at, field="expires_at")
        if expires_at <= created_at:
            raise DestructionPlanCorruptError("expires_at must be later than created_at")
        return DestructionPlan(
            plan_id=serialized.plan_id,
            operation=serialized.operation,
            target=serialized.target,
            database=serialized.database,
            metadata_database=serialized.metadata_database,
            requested_pipeline_names=serialized.requested_pipeline_names,
            included_dependent_pipeline_names=serialized.included_dependent_pipeline_names,
            affected_pipeline_names=serialized.affected_pipeline_names,
            affected_model_names=serialized.affected_model_names,
            affected_source_names=serialized.affected_source_names,
            relations=tuple(
                _relation_from_serialized(relation) for relation in serialized.relations
            ),
            challenges=serialized.challenges,
            preserves_sources=serialized.preserves_sources,
            preserves_replay_data=serialized.preserves_replay_data,
            manifest_fingerprint=serialized.manifest_fingerprint,
            plan_fingerprint=serialized.plan_fingerprint,
            created_at=created_at,
            expires_at=expires_at,
            relation_drop_size_limit=serialized.relation_drop_size_limit,
            relation_drop_size_server_limit=serialized.relation_drop_size_server_limit,
            relation_drop_size_override=serialized.relation_drop_size_override,
            relation_drop_size_policy_observed=(serialized.relation_drop_size_policy_observed),
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise DestructionPlanCorruptError(
            f"Stored destruction plan payload is incompatible or corrupt: {error}"
        ) from error


def _relation_from_serialized(relation: _SerializedRelation) -> DestructionRelationEvidence:
    return DestructionRelationEvidence(
        database=relation.database,
        name=relation.name,
        kind=relation.kind,
        exists=relation.exists,
        total_bytes=relation.total_bytes,
        active_parts=relation.active_parts,
        catalog_fingerprint=relation.catalog_fingerprint,
        logical_names=relation.logical_names,
        pipeline_names=relation.pipeline_names,
        ownership=relation.ownership,
        dependency_relation_names=relation.dependency_relation_names,
    )


def _aware_utc(*, value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise DestructionPlanCorruptError(f"{field} must include a timezone")
    return value.astimezone(UTC)
