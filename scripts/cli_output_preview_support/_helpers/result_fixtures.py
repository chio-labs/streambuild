"""Execution result fixtures for preview rendering."""

from __future__ import annotations

from scripts.cli_output_preview_support._helpers.plan_fixtures import (
    build_plan_preview,
)
from streambuild.compiler.compile.models import ObjectKey
from streambuild.executor.audit_backfill.models import (
    AuditBackfillResult,
    AuditDeploymentCandidate,
    RootAuditResult,
)
from streambuild.executor.backfill.models import (
    BackfillBootstrapResult,
    BackfillExecutionResult,
    RootBackfillReport,
)
from streambuild.executor.publish.models import PublishedView, PublishResult


def build_backfill_preview() -> BackfillExecutionResult:
    return BackfillExecutionResult(
        bootstrap=BackfillBootstrapResult(
            deployment_id="20260410T120000Z_ab12cd",
            created_at="2026-04-10 12:00:00.000",
            deployment_plan=build_plan_preview(),
            root_reports=(
                RootBackfillReport(
                    root_key=ObjectKey(None, "table", "tbl__orders_enriched"),
                    state_kind="greenfield",
                    replay_strategy="create_from_scratch",
                    active_deployment_id=None,
                ),
            ),
        ),
        boundary_time="2026-04-10 12:00:00.000",
    )


def build_audit_preview() -> AuditBackfillResult:
    return AuditBackfillResult(
        deployment_id="20260410T120000Z_ab12cd",
        deployment_status="backfilling",
        assessment="ready",
        replay_lineage_mode="offsets",
        warning_codes=(),
        root_results=(
            RootAuditResult(
                root_key=ObjectKey(None, "table", "tbl__orders_enriched"),
                staged_physical_name="tbl__orders_enriched_20260410T120000Z_ab12cd",
                staged_exists=True,
                active_exists=False,
                active_row_count=None,
                staged_row_count=1203,
                row_delta=None,
                row_ratio=None,
                state="greenfield",
                replay_source_name="raw__orders",
                replay_source_row_count=1203,
                assessment="ready",
                replay_lineage_mode="offsets",
                offset_catchup_summary=None,
                scalar_catchup_summary=None,
            ),
        ),
    )


def build_publish_preview() -> PublishResult:
    return PublishResult(
        deployment_id="20260410T120000Z_ab12cd",
        published_views=(
            PublishedView(
                view_name="tbl__orders_enriched",
                target_table_name="tbl__orders_enriched_20260410T120000Z_ab12cd",
            ),
        ),
        per_relation_atomic_replace=True,
        graph_atomic_publish=False,
    )


def build_audit_caution_preview() -> AuditBackfillResult:
    return AuditBackfillResult(
        deployment_id="20260410T120500Z_cd34ef",
        deployment_status="backfilling",
        assessment="caution",
        replay_lineage_mode="offsets",
        warning_codes=("missing_staged_active_partition",),
        root_results=(
            RootAuditResult(
                root_key=ObjectKey(None, "table", "tbl__orders_enriched"),
                staged_physical_name="tbl__orders_enriched_20260410T120500Z_cd34ef",
                staged_exists=True,
                active_exists=True,
                active_row_count=1350,
                staged_row_count=1324,
                row_delta=-26,
                row_ratio=0.98074,
                state="active_view_present",
                replay_source_name="raw__orders",
                replay_source_row_count=1350,
                assessment="caution",
                replay_lineage_mode="offsets",
                offset_catchup_summary=None,
                scalar_catchup_summary=None,
            ),
        ),
    )


def build_ambiguity_candidates() -> tuple[AuditDeploymentCandidate, ...]:
    return (
        AuditDeploymentCandidate(
            deployment_id="20260410T120500Z_cd34ef",
            created_at="2026-04-10 12:05:00.000",
            deployment_status="backfilling",
            root_names=("tbl__orders_enriched",),
        ),
        AuditDeploymentCandidate(
            deployment_id="20260410T120000Z_ab12cd",
            created_at="2026-04-10 12:00:00.000",
            deployment_status="backfilling",
            root_names=("tbl__orders_enriched",),
        ),
    )
