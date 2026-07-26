"""Neutral warehouse adapter contract."""

from abc import ABC, abstractmethod

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterConnectionConfig,
    AdapterIdentity,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
)


class Adapter(ABC):
    """A warehouse implementation that can open neutral connections."""

    @property
    @abstractmethod
    def identity(self) -> AdapterIdentity:
        """Return the registered identity of this adapter."""

    @abstractmethod
    def connect(self, config: AdapterConnectionConfig) -> AdapterConnection:
        """Open a warehouse connection for the resolved configuration."""

    @abstractmethod
    def render_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        """Render one neutral resource request into adapter SQL."""
