"""ClickHouse implementation of the neutral adapter contract."""

from __future__ import annotations

from typing import cast

import clickhouse_connect
from clickhouse_connect.driver.exceptions import ClickHouseError, StreamFailureError

from streambuild.adapter.classes.adapter import Adapter
from streambuild.adapter.models import (
    AdapterConnectionConfig,
    AdapterIdentity,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
)
from streambuild.adapters.clickhouse._helpers.errors import translate_driver_error
from streambuild.adapters.clickhouse._helpers.rendering import render_clickhouse_resource
from streambuild.adapters.clickhouse.classes.clickhouse_connection import ClickHouseConnection
from streambuild.adapters.clickhouse.constants import CLICKHOUSE_ADAPTER_NAME
from streambuild.adapters.clickhouse.types import RawClickHouseClient


class ClickHouseAdapter(Adapter):
    """The built-in ClickHouse adapter."""

    @property
    def identity(self) -> AdapterIdentity:
        """Return the registered ClickHouse adapter identity."""

        return AdapterIdentity(name=CLICKHOUSE_ADAPTER_NAME)

    def connect(self, config: AdapterConnectionConfig) -> ClickHouseConnection:
        """Open a ClickHouse connection for the resolved configuration."""

        try:
            raw_client: RawClickHouseClient = self._open_raw_client(config)
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
        return ClickHouseConnection(raw_client)

    def render_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        """Render one neutral resource request as ClickHouse SQL."""

        return render_clickhouse_resource(
            resource=resource,
            database=database,
            if_not_exists=if_not_exists,
        )

    def _open_raw_client(self, config: AdapterConnectionConfig) -> RawClickHouseClient:
        if config.database is None:
            return cast(
                RawClickHouseClient,
                clickhouse_connect.get_client(
                    host=config.host,
                    port=config.port,
                    username=config.username,
                    password=config.password,
                ),
            )
        return cast(
            RawClickHouseClient,
            clickhouse_connect.get_client(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                database=config.database,
            ),
        )
