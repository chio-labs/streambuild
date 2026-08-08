from dataclasses import dataclass

from streambuild.executor.kafka_admin.models import ConsumerGroupOffsetReset


@dataclass(frozen=True)
class FreshLandingOffsetResetTestCase:
    description: str
    created_relation_names: tuple[str, ...]
    delete_results: tuple[tuple[str, str], ...]
    expected_resets: tuple[ConsumerGroupOffsetReset, ...]
    expected_deleted_group_calls: tuple[tuple[str, ...], ...]
    expected_closed_states: tuple[bool, ...]


@dataclass(frozen=True)
class OffsetResetFailureTestCase:
    description: str
    error: str
    expected_reset: ConsumerGroupOffsetReset


@dataclass(frozen=True)
class AdminClientConfigTestCase:
    description: str
    broker_list: str
    settings: tuple[tuple[str, str], ...]
    expected_bootstrap_servers: tuple[str, ...]
    expected_config_items: tuple[tuple[str, str], ...]
