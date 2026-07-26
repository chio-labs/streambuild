from dataclasses import dataclass

from streambuild.spec.types import ReplayLineageMode


@dataclass(frozen=True)
class ExecutePublishIntegrationTestCase:
    description: str
    replay_lineage_mode: ReplayLineageMode | str
    deployment_id: str | None
    created_at: str
    boundary_time: str
    expected_view_name: str
    expected_target_table_name: str
    expected_published_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResolvePublishDeploymentIntegrationTestCase:
    description: str
    create_active_view: bool
    first_deployment_id: str
    second_deployment_id: str
    expected_resolved_deployment_id: str | None
    expected_error_fragment: str | None


@dataclass(frozen=True)
class PublishWithoutMetadataIntegrationTestCase:
    description: str
    deployment_id: str | None
    expected_deployment_id: str
    expected_target_table_name: str


@dataclass(frozen=True)
class PublishMissingStagedTableIntegrationTestCase:
    description: str
    deployment_id: str
    expected_error_fragment: str


@dataclass(frozen=True)
class PublishAfterDeletedActiveViewIntegrationTestCase:
    description: str
    active_deployment_id: str
    staged_deployment_id: str
    expected_target_table_name: str
