from streambuild.adapter.models import AdapterBindingReplacementRequest, AdapterOwnedResourceEvent
from streambuild.adapters.clickhouse._helpers.lifecycle import (
    render_clickhouse_stable_binding_replacement,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class RepairWorkflowAdapterConnection(RecordingAdapterConnection):
    def __init__(self) -> None:
        super().__init__()
        self.ownership_events: list[AdapterOwnedResourceEvent] = []

    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        return render_clickhouse_stable_binding_replacement(
            connection=self,
            request=request,
        )

    def render_owned_resource_events(
        self, *, database: str, events: tuple[AdapterOwnedResourceEvent, ...]
    ) -> tuple[str, ...]:
        del database
        self.ownership_events.extend(events)
        return ()
