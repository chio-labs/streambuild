from dataclasses import dataclass


@dataclass(frozen=True)
class ExecuteJanitorPreviewIntegrationTestCase:
    description: str
    retention_days: int
    expected_deletable_deployment_ids: tuple[str, ...]
    expected_kept_deployment_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExecuteJanitorApplyIntegrationTestCase:
    description: str
    retention_days: int
    expected_deleted_deployment_ids: tuple[str, ...]
    expected_deleted_target_tables: tuple[str, ...]
    expected_retained_target_tables: tuple[str, ...]
    expected_deployment_row_count: int
    expected_publish_history_row_count: int
