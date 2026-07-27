"""Neutral warehouse adapter contract."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterAdoptedSourceRealizationRequest,
    AdapterConnectionConfig,
    AdapterIdentity,
    AdapterManagedSource,
    AdapterManagedSourceRealizationRequest,
    AdapterMaterializedView,
    AdapterModelRealization,
    AdapterModelRealizationRequest,
    AdapterSourceRealization,
    AdapterStableView,
    AdapterTable,
)


class Adapter(ABC):
    """A warehouse implementation that can open neutral connections."""

    @property
    @abstractmethod
    def identity(self) -> AdapterIdentity:
        """Return the registered identity of this adapter."""

    @property
    @abstractmethod
    def sql_analysis_dialect(self) -> str:
        """Return the mandatory SQL analysis dialect name."""

    @property
    @abstractmethod
    def default_database(self) -> str | None:
        """Return the adapter's default database for offline target resolution."""

    @property
    @abstractmethod
    def default_schema(self) -> str | None:
        """Return the adapter's default schema for offline target resolution."""

    @abstractmethod
    def connect(self, config: AdapterConnectionConfig) -> AdapterConnection:
        """Open a warehouse connection for the resolved configuration."""

    @abstractmethod
    def build_connection_config(
        self,
        *,
        values: Mapping[str, object],
        database: str | None,
    ) -> AdapterConnectionConfig:
        """Validate adapter-owned raw values into a neutral connection config."""

    @abstractmethod
    def render_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        """Render one neutral resource request into adapter SQL."""

    @abstractmethod
    def realize_source(
        self,
        *,
        request: AdapterManagedSourceRealizationRequest | AdapterAdoptedSourceRealizationRequest,
    ) -> AdapterSourceRealization:
        """Map one logical source to its adapter relation and resources."""

    @abstractmethod
    def model_relation_name(self, *, logical_name: str) -> str:
        """Resolve the adapter relation name for one logical model."""

    @abstractmethod
    def realize_model(self, *, request: AdapterModelRealizationRequest) -> AdapterModelRealization:
        """Map one semantically compiled logical model to adapter resources."""
