from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterStableBinding,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class WrongRepairBindingAdapterConnection(RecordingAdapterConnection):
    def __init__(self, returned_bindings: tuple[AdapterStableBinding, ...]) -> None:
        super().__init__()
        self._returned_bindings: tuple[AdapterStableBinding, ...] = returned_bindings

    def replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> AdapterBindingReplacementResult:
        self.binding_requests.append(request)
        return AdapterBindingReplacementResult(
            bindings=self._returned_bindings,
            per_relation_atomic_replace=self.capabilities.per_relation_atomic_replace,
            graph_atomic_publish=self.capabilities.graph_atomic_publish,
        )
