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
    drop_all_metadata_tables: bool
    expected_actual_object_names: tuple[str, ...]


@dataclass(frozen=True)
class LoadActualStateMixedRootsIntegrationTestCase:
    description: str
    create_orders_active_view: bool
    create_orders_candidates: bool
    create_customers_active_view: bool
    create_customers_candidates: bool
    create_customers_invalid_view: bool
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
