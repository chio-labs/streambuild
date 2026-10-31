"""Build adapter-neutral metadata persistence state."""

from sqltide.adapter.models import AdapterMetadataState
from sqltide.compiler.planner._helpers.warehouse_metadata import (
    build_adapter_metadata_state as _build_adapter_metadata_state,
)
from sqltide.compiler.planner.models import MetadataState


def build_adapter_metadata_state(state: MetadataState) -> AdapterMetadataState:
    """Convert compiler metadata state into neutral adapter records."""

    return _build_adapter_metadata_state(state)
