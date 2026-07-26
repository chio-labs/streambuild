"""Resolve the configured adapter before any warehouse connection is opened."""

from streambuild.adapter._helpers.registry import build_adapter_registry, builtin_adapters
from streambuild.adapter.classes.adapter import Adapter
from streambuild.adapter.exceptions import UnknownAdapterError


def resolve_adapter(adapter_name: str) -> Adapter:
    """Return the registered adapter for a configured adapter name."""

    registry: dict[str, Adapter] = build_adapter_registry(builtin_adapters())
    adapter: Adapter | None = registry.get(adapter_name)
    if adapter is None:
        supported_names: str = ", ".join(sorted(registry))
        raise UnknownAdapterError(
            f"Unsupported adapter '{adapter_name}'. Supported adapters: {supported_names}."
        )
    return adapter
