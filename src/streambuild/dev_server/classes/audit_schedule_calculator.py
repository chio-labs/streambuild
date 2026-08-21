"""Calculate audit due states from compiled policy and warehouse metadata."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.quality.types import QualityNodeKind
from streambuild.dev_server._helpers.queries.runs_query import (
    read_latest_direct_build_materialization,
)
from streambuild.dev_server._helpers.server.checks_execution import build_checks_status_payload
from streambuild.dev_server.constants import IDENTITY_DRIFT_STATUSES
from streambuild.dev_server.types import AuditScheduleState
from streambuild.executor.auditing.main.load_materialized_model_names import (
    load_materialized_model_names,
)
from streambuild.executor.auditing.main.load_model_anchors import load_model_anchors
from streambuild.executor.auditing.main.resolve_audit_warmup_states import (
    resolve_audit_warmup_states,
)
from streambuild.executor.auditing.models import AuditWarmupState
from streambuild.executor.auditing.types import QualityResultStatus
from streambuild.executor.observability.main.logical_project_identity import (
    logical_project_identity,
)
from streambuild.executor.observability.types import MaterializationOutcome


class AuditScheduleCalculator:
    """Build a dry-run scheduler payload for one compiled target."""

    def __init__(
        self,
        *,
        analysis: CompileAnalysis,
        connection: AdapterConnection,
        database: str,
        project_dir: Path,
    ) -> None:
        self._analysis = analysis
        self._connection = connection
        self._database = database
        self._project_dir = project_dir

    def build_payload(self, *, enabled: bool) -> dict[str, object]:
        audits: tuple[LoadedSqlAudit, ...] = tuple(
            audit for audit in self._analysis.compiled_project.audits if audit.scheduled
        )
        warehouse_now: str = self._connection.capture_warehouse_timestamp()
        if not audits:
            return {
                "enabled": enabled,
                "state": AuditScheduleState.IDLE if enabled else AuditScheduleState.DISABLED,
                "warehouseNow": warehouse_now,
                "dueCount": 0,
                "audits": [],
            }
        anchors: dict[str, str] = load_model_anchors(
            client=self._connection,
            metadata_database=self._database,
            target_database=self._database,
            model_names=self._referenced_model_names(audits),
            virtual_environments=self._analysis.compile_inputs.virtual_environments,
        )
        materialized_model_names: frozenset[str] = load_materialized_model_names(
            client=self._connection,
            database=self._database,
            relation_name_by_model={
                model.key.name: self._analysis.realized_project.relation_name_by_logical_key[
                    model.key
                ]
                for model in self._analysis.compiled_project.models
            },
        )
        warmup_states: dict[str, AuditWarmupState] = resolve_audit_warmup_states(
            audits=audits,
            anchors_by_model=anchors,
            materialized_model_names=materialized_model_names,
            warehouse_now=warehouse_now,
        )
        status_by_name: dict[str, dict[str, object]] = {
            str(status["name"]): status
            for status in build_checks_status_payload(
                analysis=self._analysis,
                connection=self._connection,
                database=self._database,
                project_dir=self._project_dir,
            )
            if status["kind"] == QualityNodeKind.AUDIT
        }
        audit_states: list[dict[str, object]] = [
            self._audit_schedule_payload(
                audit=audit,
                warmup=warmup_states[audit.name or audit.file_path.stem],
                status=status_by_name.get(audit.name or audit.file_path.stem),
                warehouse_now=warehouse_now,
                anchors=anchors,
            )
            for audit in audits
        ]
        blocked_by_failed_build: bool = (
            read_latest_direct_build_materialization(
                connection=self._connection,
                database=self._database,
                project_identity=logical_project_identity(project_dir=self._project_dir),
            )
            == MaterializationOutcome.FAILED
        )
        if blocked_by_failed_build:
            for audit_state in audit_states:
                if audit_state["state"] == AuditScheduleState.NOT_MATERIALIZED:
                    continue
                audit_state["state"] = AuditScheduleState.BLOCKED
                audit_state["blockedReason"] = "failed_build"
        due_count: int = sum(1 for item in audit_states if item["state"] == AuditScheduleState.DUE)
        return {
            "enabled": enabled,
            "state": (
                AuditScheduleState.DISABLED
                if not enabled
                else (
                    AuditScheduleState.BLOCKED
                    if blocked_by_failed_build
                    else (AuditScheduleState.DUE if due_count else AuditScheduleState.IDLE)
                )
            ),
            "warehouseNow": warehouse_now,
            "dueCount": due_count,
            "audits": audit_states,
        }

    def _audit_schedule_payload(
        self,
        *,
        audit: LoadedSqlAudit,
        warmup: AuditWarmupState,
        status: dict[str, object] | None,
        warehouse_now: str,
        anchors: dict[str, str],
    ) -> dict[str, object]:
        now: datetime = self._timestamp(warehouse_now)
        eligible_at: datetime = self._timestamp(warmup.eligible_at or warehouse_now)
        completed_at_value: str | None = (
            None if status is None else self._optional_string(status.get("completedAt"))
        )
        status_value: str = "never_run" if status is None else str(status["status"])
        if warmup.missing_model_names:
            scheduled_for: datetime | None = None
            state: AuditScheduleState = AuditScheduleState.NOT_MATERIALIZED
        elif not warmup.eligible:
            scheduled_for = eligible_at
            state: AuditScheduleState = AuditScheduleState.WARMING_UP
        elif completed_at_value is None:
            scheduled_for = (
                eligible_at
                if warmup.anchor is not None
                else self._cadence_slot(now=now, cadence_seconds=audit.cadence_seconds)
            )
            state = AuditScheduleState.DUE if now >= scheduled_for else AuditScheduleState.SCHEDULED
        else:
            completed_at: datetime = self._timestamp(completed_at_value)
            newest_anchor: datetime | None = max(
                (
                    self._timestamp(anchors[name])
                    for name in audit.referenced_model_names
                    if name in anchors
                ),
                default=None,
            )
            if status_value in IDENTITY_DRIFT_STATUSES:
                scheduled_for = max(
                    self._cadence_slot(now=now, cadence_seconds=audit.cadence_seconds),
                    eligible_at,
                )
            elif status_value == QualityResultStatus.DEFERRED or (
                newest_anchor is not None and newest_anchor > completed_at
            ):
                scheduled_for = eligible_at
            else:
                scheduled_for = max(
                    completed_at + timedelta(seconds=int(audit.cadence_seconds or 0)),
                    eligible_at,
                )
            state = AuditScheduleState.DUE if now >= scheduled_for else AuditScheduleState.SCHEDULED
        return {
            "name": audit.name or audit.file_path.stem,
            "state": state,
            "scheduledFor": (
                None if scheduled_for is None else self._render_timestamp(scheduled_for)
            ),
            "eligibleAt": warmup.eligible_at,
            "anchor": warmup.anchor,
            "cadenceSeconds": audit.cadence_seconds,
            "warmupSeconds": audit.warmup_seconds,
            "lastStatus": status_value,
            "referencedModels": list(audit.referenced_model_names),
            "missingRelations": list(warmup.missing_model_names),
        }

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _referenced_model_names(audits: tuple[LoadedSqlAudit, ...]) -> tuple[str, ...]:
        model_names: set[str] = set()
        for audit in audits:
            model_names.update(audit.referenced_model_names)
        return tuple(sorted(model_names))

    @staticmethod
    def _timestamp(value: str) -> datetime:
        parsed: datetime = datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

    @staticmethod
    def _render_timestamp(value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @staticmethod
    def _cadence_slot(*, now: datetime, cadence_seconds: int | None) -> datetime:
        cadence: int = int(cadence_seconds or 1)
        slot_timestamp: int = int(now.timestamp()) // cadence * cadence
        return datetime.fromtimestamp(slot_timestamp, tz=UTC)
