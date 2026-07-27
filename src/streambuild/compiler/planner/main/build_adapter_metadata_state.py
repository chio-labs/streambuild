"""Build adapter-neutral metadata persistence state."""

from streambuild.adapter.models import AdapterMetadataState
from streambuild.compiler.planner._helpers.warehouse_metadata import (
    build_adapter_metadata_state as _build_adapter_metadata_state,
)
from streambuild.compiler.planner.models import MetadataState


def build_adapter_metadata_state(state: MetadataState) -> AdapterMetadataState:
    """Convert compiler metadata state into neutral adapter records."""

    return _build_adapter_metadata_state(state)
