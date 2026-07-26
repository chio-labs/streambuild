from collections.abc import Callable
from dataclasses import dataclass

from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.models import DesiredState


@dataclass(frozen=True)
class ExecuteReconcileTestCase:
    description: str
    build_states: Callable[[], tuple[DesiredState, ActualState]]
    expected_eligible_names: tuple[str, ...]
    expected_rejected_reason_groups: tuple[tuple[str, ...], ...]
    expected_reconcile_id_prefix: str
