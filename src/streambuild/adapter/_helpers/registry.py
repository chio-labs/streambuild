"""Built-in adapter registration and duplicate-name rejection."""

from streambuild.adapter.classes.adapter import Adapter
from streambuild.adapter.exceptions import DuplicateAdapterError


def build_adapter_registry(adapters: tuple[Adapter, ...]) -> dict[str, Adapter]:
    """Index adapters by registered name, rejecting duplicate registrations."""

    registry: dict[str, Adapter] = {}
    adapter: Adapter
    for adapter in adapters:
        adapter_name: str = adapter.identity.name
        if adapter_name in registry:
            raise DuplicateAdapterError(
                f"Duplicate adapter name '{adapter_name}' registered by "
                f"{type(registry[adapter_name]).__name__} and {type(adapter).__name__}"
            )
        registry[adapter_name] = adapter
    return registry


def builtin_adapters() -> tuple[Adapter, ...]:
    """Return every adapter implementation shipped with StreamBuild."""

    from streambuild.adapters.clickhouse.main.build_clickhouse_adapter import (
        build_clickhouse_adapter,
    )

    return (build_clickhouse_adapter(),)
