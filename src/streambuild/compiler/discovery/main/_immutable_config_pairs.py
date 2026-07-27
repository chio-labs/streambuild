"""Build deeply immutable authored configuration pairs."""

from collections.abc import Mapping
from types import MappingProxyType


def immutable_config_pairs(
    values: tuple[tuple[str, object], ...],
) -> tuple[tuple[str, object], ...]:
    """Freeze nested values while preserving stable authored key ordering."""

    return tuple((key, _immutable_config_value(value)) for key, value in values)


def _immutable_config_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _immutable_config_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_immutable_config_value(item) for item in value)
    return value
