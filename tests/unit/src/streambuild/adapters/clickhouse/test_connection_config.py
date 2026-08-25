import clickhouse_connect
import pytest

from streambuild.adapter.exceptions import AdapterConfigurationError
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.adapters.clickhouse.classes.clickhouse_connection import ClickHouseConnection
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    ClickHouseConnectionConfigErrorTestCase,
    ClickHouseConnectionDriverSettingsTestCase,
    ClickHouseConnectionReprTestCase,
    ClickHouseConnectionSettingsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseConnectionConfigErrorTestCase(
            description="rejects adapter-owned connection fields not exercised by ClickHouse",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
                ("warehouse", "analytics"),
            ),
            expected_error_fragment="unsupported fields: warehouse",
        ),
        ClickHouseConnectionConfigErrorTestCase(
            description="rejects a non-integer ClickHouse port",
            values=(
                ("host", "localhost"),
                ("port", "8123"),
                ("username", "streambuild"),
                ("password", "secret"),
            ),
            expected_error_fragment="requires integer port",
        ),
        ClickHouseConnectionConfigErrorTestCase(
            description="rejects connection settings declared as a scalar",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
                ("settings", "max_threads=8"),
            ),
            expected_error_fragment="settings requires a table of setting values",
        ),
        ClickHouseConnectionConfigErrorTestCase(
            description="rejects a connection setting value that is not a scalar",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
                ("settings", {"max_threads": ["8"]}),
            ),
            expected_error_fragment="setting max_threads requires a string, number, or boolean",
        ),
        ClickHouseConnectionConfigErrorTestCase(
            description="rejects an empty connection setting name",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
                ("settings", {"": "8"}),
            ),
            expected_error_fragment="requires non-empty setting names",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_connection_fields_when_building_config_then_adapter_rejects_them(
    test_case: ClickHouseConnectionConfigErrorTestCase,
) -> None:
    with pytest.raises(AdapterConfigurationError, match=test_case.expected_error_fragment):
        ClickHouseAdapter().build_connection_config(
            values=dict(test_case.values),
            database="analytics",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseConnectionSettingsTestCase(
            description="defaults to no settings when the connection omits them",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
            ),
            expected_settings=(),
        ),
        ClickHouseConnectionSettingsTestCase(
            description="normalizes declared settings into ordered string pairs",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
                (
                    "settings",
                    {
                        "max_threads": 8,
                        "max_memory_usage": "16000000000",
                        "join_use_nulls": True,
                        "max_execution_time": 0,
                    },
                ),
            ),
            expected_settings=(
                ("join_use_nulls", "1"),
                ("max_execution_time", "0"),
                ("max_memory_usage", "16000000000"),
                ("max_threads", "8"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_declared_connection_settings_when_building_config_then_adapter_normalizes_them(
    test_case: ClickHouseConnectionSettingsTestCase,
) -> None:
    config: AdapterConnectionConfig = ClickHouseAdapter().build_connection_config(
        values=dict(test_case.values),
        database="analytics",
    )

    assert config.settings == test_case.expected_settings


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseConnectionDriverSettingsTestCase(
            description="forwards declared settings to the database-scoped driver client",
            database="analytics",
            settings=(("max_memory_usage", "16000000000"), ("max_threads", "8")),
            destruction_relation_drop_size_limit=107_374_182_400,
            expected_driver_settings=(
                ("max_memory_usage", "16000000000"),
                ("max_threads", "8"),
            ),
            expected_destruction_relation_drop_size_limit=107_374_182_400,
        ),
        ClickHouseConnectionDriverSettingsTestCase(
            description="forwards declared settings when no database is scoped",
            database=None,
            settings=(("max_threads", "8"),),
            destruction_relation_drop_size_limit=None,
            expected_driver_settings=(("max_threads", "8"),),
            expected_destruction_relation_drop_size_limit=None,
        ),
        ClickHouseConnectionDriverSettingsTestCase(
            description="sends no driver settings when the connection declares none",
            database="analytics",
            settings=(),
            destruction_relation_drop_size_limit=107_374_182_400,
            expected_driver_settings=(),
            expected_destruction_relation_drop_size_limit=107_374_182_400,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_connection_settings_when_connecting_then_driver_receives_them(
    test_case: ClickHouseConnectionDriverSettingsTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_get_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(clickhouse_connect, "get_client", fake_get_client)

    connection: ClickHouseConnection = ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host="localhost",
            port=8123,
            username="streambuild",
            password="secret",
            database=test_case.database,
            settings=test_case.settings,
            destruction_relation_drop_size_limit=(test_case.destruction_relation_drop_size_limit),
        )
    )

    assert captured["settings"] == dict(test_case.expected_driver_settings)
    assert (
        connection.destruction_relation_drop_size_limit
        == test_case.expected_destruction_relation_drop_size_limit
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseConnectionReprTestCase(
            description="renders settings while keeping the password redacted",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
                ("settings", {"max_threads": 8}),
            ),
            expected_fragments=("('max_threads', '8')",),
            expected_absent_fragments=("secret",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_connection_settings_when_rendering_repr_then_password_stays_redacted(
    test_case: ClickHouseConnectionReprTestCase,
) -> None:
    config: AdapterConnectionConfig = ClickHouseAdapter().build_connection_config(
        values=dict(test_case.values),
        database="analytics",
    )

    rendered: str = repr(config)

    assert all(fragment in rendered for fragment in test_case.expected_fragments)
    assert all(fragment not in rendered for fragment in test_case.expected_absent_fragments)
