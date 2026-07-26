"""Neutral warehouse adapter contract."""

from abc import ABC, abstractmethod

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterConnectionConfig, AdapterIdentity


class Adapter(ABC):
    """A warehouse implementation that can open neutral connections."""

    @property
    @abstractmethod
    def identity(self) -> AdapterIdentity:
        """Return the registered identity of this adapter."""

    @abstractmethod
    def connect(self, config: AdapterConnectionConfig) -> AdapterConnection:
        """Open a warehouse connection for the resolved configuration."""
