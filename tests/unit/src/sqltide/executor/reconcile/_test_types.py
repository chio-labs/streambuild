from collections.abc import Callable
from dataclasses import dataclass

from sqltide.compiler.compile.models import DesiredState
from sqltide.compiler.planner.models import ActualState


@dataclass(frozen=True)
class ExecuteReconcileTestCase:
    description: str
    build_states: Callable[[], tuple[DesiredState, ActualState]]
    expected_eligible_names: tuple[str, ...]
    expected_rejected_reason_groups: tuple[tuple[str, ...], ...]
    expected_reconcile_id_prefix: str


@dataclass(frozen=True)
class ApplyReconcileWorkflowTestCase:
    description: str
    expected_lock_database: str
    expected_migration_statement: str
    expected_object_names: tuple[str, ...]
    expected_reconcile_id_prefix: str
    expected_table_fingerprint: str
    expected_view_fingerprint: str


@dataclass(frozen=True)
class DirectReconcileTestCase:
    description: str
    expected_target_names: tuple[str, ...]
