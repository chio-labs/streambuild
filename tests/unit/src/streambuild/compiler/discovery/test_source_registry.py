from pathlib import Path
from typing import cast

import pytest

from streambuild.compiler.discovery._helpers.source_registry import discover_source_registry
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import (
    DiscoveredSourceFile,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedProject,
    ReplayBoundary,
    SourceFreshnessPolicy,
)
from tests.unit.src.streambuild.compiler.discovery._test_types import (
    KafkaBrokerDefaultTestCase,
    ProjectKafkaBrokerDefaultTestCase,
    SourceBoundaryModeTestCase,
    SourceFreshnessTestCase,
    SourceRegistryErrorTestCase,
    SourceRegistryTestCase,
)
from tests.unit.src.streambuild.compiler.discovery.helpers import (
    flatten_source_registry,
    write_source_yml,
)

_KAFKA_SOURCE_WITH_FRESHNESS: str = """
sources:
  - name: orders
    kind: kafka
    broker_list: broker:9092
    topic: orders.live
    replay_boundary:
      mode: offsets
    freshness:
      warn_after: 15m
      error_after: 1h
"""

_KAFKA_SOURCE_WITHOUT_FRESHNESS: str = """
sources:
  - name: orders
    kind: kafka
    broker_list: broker:9092
    topic: orders.live
    replay_boundary:
      mode: offsets
"""

_ADOPTED_SOURCE_WITH_FRESHNESS: str = """
sources:
  - name: orders
    kind: stream_table
    table_name: raw_orders
    replay_boundary:
      mode: cursor
      columns:
        _replay_cursor: event_cursor
        _replay_timestamp: event_timestamp
    freshness:
      error_after: 2d
"""


@pytest.mark.parametrize(
    "test_case",
    [
        SourceRegistryTestCase(
            description="loads managed and adopted sources once in stable file order",
            expected_source_names=("orders", "external_orders"),
            expected_boundary_modes=("offsets", "cursor"),
            expected_relative_paths=("sources/a.yml", "sources/z.yml"),
            expected_managed_source_ttl="_replay_landed_at + INTERVAL 14 DAY",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_files_when_discovering_then_returns_stable_typed_registry(
    test_case: SourceRegistryTestCase,
    tmp_path: Path,
) -> None:
    write_source_yml(
        project_dir=tmp_path,
        relative_path="z.yml",
        contents="""
        sources:
          - name: external_orders
            kind: stream_table
            table_name: "${table_name}"
            replay_boundary:
              mode: cursor
              columns:
                _replay_cursor: event_cursor
                _replay_timestamp: event_timestamp
        """,
    )
    write_source_yml(
        project_dir=tmp_path,
        relative_path="a.yml",
        contents="""
        sources:
          - name: orders
            kind: kafka
            broker_list: "${ENV:BROKER_LIST}"
            topic: source.orders
            ttl: "_replay_landed_at + INTERVAL ${ttl_days} DAY"
            replay_boundary:
              mode: offsets
        """,
    )

    source_files: tuple[DiscoveredSourceFile, ...] = discover_source_registry(
        project_dir=tmp_path,
        variables={"table_name": "orders_existing", "ttl_days": 14},
        environment={"BROKER_LIST": "redpanda:9092"},
    )
    sources: tuple[KafkaLandingStep | ExternalTableSourceStep, ...] = flatten_source_registry(
        source_files
    )

    assert tuple(source.name for source in sources) == test_case.expected_source_names
    assert (
        tuple(cast(ReplayBoundary, source.replay_boundary).mode for source in sources)
        == test_case.expected_boundary_modes
    )
    assert tuple(str(item.source_file.relative_path) for item in source_files) == (
        test_case.expected_relative_paths
    )
    managed_source: KafkaLandingStep = cast(KafkaLandingStep, sources[0])
    assert managed_source.kafka.ttl == test_case.expected_managed_source_ttl


@pytest.mark.parametrize(
    "test_case",
    [
        KafkaBrokerDefaultTestCase(
            description="project brokers supply an omitted source value",
            source_broker_yaml="",
            default_broker_list="kafka1:9092,kafka2:9092",
            expected_broker_list="kafka1:9092,kafka2:9092",
        ),
        KafkaBrokerDefaultTestCase(
            description="source brokers override the project default",
            source_broker_yaml="broker_list: source-kafka:9092",
            default_broker_list="project-kafka:9092",
            expected_broker_list="source-kafka:9092",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_kafka_broker_defaults_when_discovering_source_then_applies_precedence(
    test_case: KafkaBrokerDefaultTestCase,
    tmp_path: Path,
) -> None:
    write_source_yml(
        project_dir=tmp_path,
        relative_path="events.yml",
        contents=f"""
        sources:
          - name: events
            kind: kafka
            {test_case.source_broker_yaml}
            topic: source.events
            replay_boundary: {{mode: offsets}}
        """,
    )

    source_files: tuple[DiscoveredSourceFile, ...] = discover_source_registry(
        project_dir=tmp_path,
        variables={},
        environment={},
        default_kafka_broker_list=test_case.default_broker_list,
    )

    source: KafkaLandingStep = cast(KafkaLandingStep, flatten_source_registry(source_files)[0])
    assert source.kafka.broker_list == test_case.expected_broker_list


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectKafkaBrokerDefaultTestCase(
            description="interpolated project brokers reach source discovery",
            configured_broker_list="${ENV:KAFKA_BROKERS}",
            environment=(("KAFKA_BROKERS", "kafka1:9092,kafka2:9092"),),
            expected_broker_list="kafka1:9092,kafka2:9092",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interpolated_project_kafka_default_when_loading_project_then_source_inherits_it(
    test_case: ProjectKafkaBrokerDefaultTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "streambuild_project.toml").write_text(
        f"""
name = "events"
default_target = "test"

[defaults]
kafka_broker_list = "{test_case.configured_broker_list}"

[targets.test]
""".strip(),
        encoding="utf-8",
    )
    write_source_yml(
        project_dir=tmp_path,
        relative_path="events.yml",
        contents="""
        sources:
          - name: events
            kind: kafka
            topic: source.events
            replay_boundary: {mode: offsets}
        """,
    )

    loaded: LoadedProject | None = load_project_input_for_path(
        path=tmp_path,
        environment=dict(test_case.environment),
    )

    assert loaded is not None
    source: KafkaLandingStep = cast(
        KafkaLandingStep, flatten_source_registry(loaded.source_files)[0]
    )
    assert source.kafka.broker_list == test_case.expected_broker_list


@pytest.mark.parametrize(
    "test_case",
    [
        SourceBoundaryModeTestCase(
            description="loads managed offset boundary",
            source_contents="""
            sources:
              - name: events
                kind: kafka
                broker_list: redpanda:9092
                topic: source.events
                replay_boundary: {mode: offsets}
            """,
            expected_source_type_name="KafkaLandingStep",
            expected_mode="offsets",
            expected_columns=(None, None, None, None, None),
        ),
        SourceBoundaryModeTestCase(
            description="loads managed timestamp boundary",
            source_contents="""
            sources:
              - name: events
                kind: kafka
                broker_list: redpanda:9092
                topic: source.events
                replay_boundary: {mode: timestamp}
            """,
            expected_source_type_name="KafkaLandingStep",
            expected_mode="timestamp",
            expected_columns=(None, None, None, None, None),
        ),
        SourceBoundaryModeTestCase(
            description="interpolates managed kind and timestamp boundary mode",
            source_contents="""
            sources:
              - name: events
                kind: "${source_kind}"
                broker_list: redpanda:9092
                topic: source.events
                replay_boundary: {mode: "${boundary_mode}"}
            """,
            expected_source_type_name="KafkaLandingStep",
            expected_mode="timestamp",
            expected_columns=(None, None, None, None, None),
            variables=(("boundary_mode", "timestamp"), ("source_kind", "kafka")),
        ),
        SourceBoundaryModeTestCase(
            description="loads managed landed-at boundary",
            source_contents="""
            sources:
              - name: events
                kind: kafka
                broker_list: redpanda:9092
                topic: source.events
                replay_boundary: {mode: landed_at}
            """,
            expected_source_type_name="KafkaLandingStep",
            expected_mode="landed_at",
            expected_columns=(None, None, None, None, None),
        ),
        SourceBoundaryModeTestCase(
            description="loads adopted offset boundary roles",
            source_contents="""
            sources:
              - name: events
                kind: stream_table
                table_name: events_existing
                replay_boundary:
                  mode: offsets
                  columns:
                    _replay_partition: physical_partition
                    _replay_offset: physical_offset
                    _replay_timestamp: physical_timestamp
            """,
            expected_source_type_name="ExternalTableSourceStep",
            expected_mode="offsets",
            expected_columns=(
                "physical_partition",
                "physical_offset",
                "physical_timestamp",
                None,
                None,
            ),
        ),
        SourceBoundaryModeTestCase(
            description="loads adopted timestamp boundary role",
            source_contents="""
            sources:
              - name: events
                kind: stream_table
                table_name: events_existing
                replay_boundary:
                  mode: timestamp
                  columns: {_replay_timestamp: physical_timestamp}
            """,
            expected_source_type_name="ExternalTableSourceStep",
            expected_mode="timestamp",
            expected_columns=(None, None, "physical_timestamp", None, None),
        ),
        SourceBoundaryModeTestCase(
            description="loads adopted cursor boundary roles",
            source_contents="""
            sources:
              - name: events
                kind: stream_table
                table_name: events_existing
                replay_boundary:
                  mode: cursor
                  columns:
                    _replay_cursor: physical_cursor
                    _replay_timestamp: physical_timestamp
            """,
            expected_source_type_name="ExternalTableSourceStep",
            expected_mode="cursor",
            expected_columns=(None, None, "physical_timestamp", None, "physical_cursor"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_source_mode_when_discovering_then_it_retains_boundary_contract(
    test_case: SourceBoundaryModeTestCase,
    tmp_path: Path,
) -> None:
    write_source_yml(
        project_dir=tmp_path,
        relative_path="events.yml",
        contents=test_case.source_contents,
    )

    source_files: tuple[DiscoveredSourceFile, ...] = discover_source_registry(
        project_dir=tmp_path,
        variables=dict(test_case.variables),
        environment={},
    )
    source: KafkaLandingStep | ExternalTableSourceStep = source_files[0].sources[0]
    boundary: ReplayBoundary = cast(ReplayBoundary, source.replay_boundary)

    assert type(source).__name__ == test_case.expected_source_type_name
    assert boundary.mode == test_case.expected_mode
    assert (
        boundary.columns.partition,
        boundary.columns.offset,
        boundary.columns.timestamp,
        boundary.columns.landed_at,
        boundary.columns.cursor,
    ) == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        SourceRegistryErrorTestCase(
            description="rejects duplicate source names with both authored paths",
            source_files=(
                (
                    "a.yml",
                    """
                    sources:
                      - name: orders
                        kind: kafka
                        broker_list: redpanda:9092
                        topic: source.orders
                        replay_boundary: {mode: offsets}
                    """,
                ),
                (
                    "b.yml",
                    """
                    sources:
                      - name: orders
                        kind: kafka
                        broker_list: redpanda:9092
                        topic: source.other
                        replay_boundary: {mode: timestamp}
                    """,
                ),
            ),
            expected_error_fragment=(
                "Duplicate source name 'orders' found in .*sources/a.yml.*sources/b.yml"
            ),
        ),
        SourceRegistryErrorTestCase(
            description="rejects managed and adopted field mixing",
            source_files=(
                (
                    "mixed.yml",
                    """
                    sources:
                      - name: orders
                        kind: stream_table
                        table_name: orders_existing
                        topic: source.orders
                        replay_boundary:
                          mode: timestamp
                          columns: {_replay_timestamp: event_timestamp}
                    """,
                ),
            ),
            expected_error_fragment="must not mix adopted and Kafka fields: topic",
        ),
        SourceRegistryErrorTestCase(
            description="rejects TTL on an adopted source",
            source_files=(
                (
                    "adopted_ttl.yml",
                    """
                    sources:
                      - name: orders
                        kind: stream_table
                        table_name: orders_existing
                        ttl: _replay_landed_at + INTERVAL 7 DAY
                        replay_boundary:
                          mode: timestamp
                          columns: {_replay_timestamp: event_timestamp}
                    """,
                ),
            ),
            expected_error_fragment="must not mix adopted and Kafka fields: ttl",
        ),
        SourceRegistryErrorTestCase(
            description="rejects managed cursor mode",
            source_files=(
                (
                    "managed_cursor.yml",
                    """
                sources:
                  - name: events
                    kind: kafka
                    broker_list: redpanda:9092
                    topic: source.events
                    replay_boundary: {mode: cursor}
                """,
                ),
            ),
            expected_error_fragment="mode 'cursor' must be one of",
        ),
        SourceRegistryErrorTestCase(
            description="rejects adopted landed-at mode",
            source_files=(
                (
                    "adopted_landed.yml",
                    """
                sources:
                  - name: events
                    kind: stream_table
                    table_name: events_existing
                    replay_boundary:
                      mode: landed_at
                      columns: {_replay_landed_at: physical_landed_at}
                """,
                ),
            ),
            expected_error_fragment="mode 'landed_at' must be one of",
        ),
        SourceRegistryErrorTestCase(
            description="rejects missing adopted offset roles",
            source_files=(
                (
                    "missing_roles.yml",
                    """
                sources:
                  - name: events
                    kind: stream_table
                    table_name: events_existing
                    replay_boundary:
                      mode: offsets
                      columns: {_replay_partition: physical_partition}
                """,
                ),
            ),
            expected_error_fragment="offsets mode requires partition, offset, and timestamp",
        ),
        SourceRegistryErrorTestCase(
            description="rejects unknown source fields with source path",
            source_files=(
                (
                    "unknown.yml",
                    """
                sources:
                  - name: events
                    kind: kafka
                    broker_list: redpanda:9092
                    topic: source.events
                    replay_boundary: {mode: offsets}
                    batch_size: 10
                """,
                ),
            ),
            expected_error_fragment="sources/unknown.yml.*unsupported keys: batch_size",
        ),
        SourceRegistryErrorTestCase(
            description="rejects interpolation in source setting keys",
            source_files=(
                (
                    "key.yml",
                    """
                sources:
                  - name: events
                    kind: kafka
                    broker_list: redpanda:9092
                    topic: source.events
                    replay_boundary: {mode: offsets}
                    settings: {"${setting_name}": "2"}
                """,
                ),
            ),
            expected_error_fragment="must not interpolate mapping keys",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_source_registry_when_discovering_then_rejects_with_paths(
    test_case: SourceRegistryErrorTestCase,
    tmp_path: Path,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.source_files:
        write_source_yml(
            project_dir=tmp_path,
            relative_path=relative_path,
            contents=contents,
        )

    with pytest.raises(PipelineDiscoveryError, match=test_case.expected_error_fragment):
        discover_source_registry(project_dir=tmp_path, variables={}, environment={})


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessTestCase(
            description="parses a managed source freshness policy",
            source_yaml=_KAFKA_SOURCE_WITH_FRESHNESS,
            default_freshness=None,
            expected_freshness=SourceFreshnessPolicy(warn_after="15m", error_after="1h"),
        ),
        SourceFreshnessTestCase(
            description="parses an adopted source freshness policy",
            source_yaml=_ADOPTED_SOURCE_WITH_FRESHNESS,
            default_freshness=None,
            expected_freshness=SourceFreshnessPolicy(error_after="2d"),
        ),
        SourceFreshnessTestCase(
            description="falls back to the project default freshness policy",
            source_yaml=_KAFKA_SOURCE_WITHOUT_FRESHNESS,
            default_freshness=SourceFreshnessPolicy(warn_after="30m"),
            expected_freshness=SourceFreshnessPolicy(warn_after="30m"),
        ),
        SourceFreshnessTestCase(
            description="prefers the source policy over the project default",
            source_yaml=_KAFKA_SOURCE_WITH_FRESHNESS,
            default_freshness=SourceFreshnessPolicy(warn_after="30m"),
            expected_freshness=SourceFreshnessPolicy(warn_after="15m", error_after="1h"),
        ),
        SourceFreshnessTestCase(
            description="defaults an absent freshness policy to none",
            source_yaml=_KAFKA_SOURCE_WITHOUT_FRESHNESS,
            default_freshness=None,
            expected_freshness=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_freshness_config_when_discovering_then_returns_expected_policy(
    test_case: SourceFreshnessTestCase,
    tmp_path: Path,
) -> None:
    write_source_yml(project_dir=tmp_path, relative_path="a.yml", contents=test_case.source_yaml)

    registry: tuple[DiscoveredSourceFile, ...] = discover_source_registry(
        project_dir=tmp_path,
        variables={},
        environment={},
        default_freshness=test_case.default_freshness,
    )

    source: KafkaLandingStep | ExternalTableSourceStep = flatten_source_registry(registry)[0]
    assert source.freshness == test_case.expected_freshness
