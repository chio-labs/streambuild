"""Private-connection reads for the background warehouse overlay."""

from __future__ import annotations

from collections.abc import Callable

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.payloads.state_payload import build_state_payload
from streambuild.dev_server.classes.kafka_lag_reader import KafkaLagReader
from streambuild.dev_server.classes.warehouse_health_reader import WarehouseHealthReader


class OverlayReader:
    """Own one private connection so overlay refreshes never take the shared query lock."""

    def __init__(
        self,
        *,
        connection_factory: Callable[[], AdapterConnection],
        kafka_lag_reader: KafkaLagReader,
    ) -> None:
        self._connection_factory = connection_factory
        self._kafka_lag_reader = kafka_lag_reader
        self._connection: AdapterConnection | None = None
        self._warehouse_health_reader: WarehouseHealthReader = WarehouseHealthReader()

    def close(self) -> None:
        """Close the private connection so the snapshot releases it on shutdown."""

        connection: AdapterConnection | None = self._connection
        self._connection = None
        if connection is not None:
            connection.close()

    def read(self, *, analysis: CompileAnalysis, database: str) -> dict[str, object]:
        """Read the overlay, discarding the connection so the next read reconnects."""

        if self._connection is None:
            self._connection = self._connection_factory()
        try:
            return build_state_payload(
                analysis=analysis,
                connection=self._connection,
                database=database,
                kafka_lag_reader=self._kafka_lag_reader,
                warehouse_health_reader=self._warehouse_health_reader,
            )
        except AdapterError:
            self.close()
            raise
