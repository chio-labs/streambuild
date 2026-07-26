from dataclasses import dataclass


@dataclass(frozen=True)
class LoadActualStateIntegrationTestCase:
    description: str
    setup_steps: tuple[str, ...]
    expected_actual_object_names: tuple[str, ...]
    expected_error_fragment: str | None


@dataclass(frozen=True)
class LoadActualStateWithoutMetadataIntegrationTestCase:
    description: str
    dropped_metadata_tables: tuple[str, ...]
    expected_actual_object_names: tuple[str, ...]


@dataclass(frozen=True)
class LoadActualStateMixedRootsIntegrationTestCase:
    description: str
    setup_steps: tuple[str, ...]
    expected_actual_object_names: tuple[str, ...]


@dataclass(frozen=True)
class LoadActualStateWithConflictingMetadataIntegrationTestCase:
    description: str
    expected_actual_object_names: tuple[str, ...]


@dataclass(frozen=True)
class LoadActualStateWithLatestObjectStateIntegrationTestCase:
    description: str
    latest_record_deployment_id: str
    latest_record_query: str
    expected_materialized_view_query: str
