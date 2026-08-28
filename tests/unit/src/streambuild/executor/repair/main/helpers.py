from streambuild.adapter.models import AdapterBindingReplacementRequest
from streambuild.adapters.clickhouse._helpers.lifecycle import (
    render_clickhouse_stable_binding_replacement,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class RepairWorkflowAdapterConnection(RecordingAdapterConnection):
    def __init__(self) -> None:
        super().__init__()

    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        return render_clickhouse_stable_binding_replacement(
            connection=self,
            request=request,
        )
