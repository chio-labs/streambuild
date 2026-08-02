"""Fix one virtual build identity before connected planning."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from streambuild.compiler.planner.constants import DEPLOYMENT_ID_PATTERN
from streambuild.executor.backfill._helpers.timing import build_current_timestamp
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.backfill.models import BackfillDeploymentIdentity


def build_backfill_deployment_identity(*, deployment_id: str | None) -> BackfillDeploymentIdentity:
    """Build the identity shared by a confirmed plan and its execution."""

    created_at: str = build_current_timestamp()
    resolved_deployment_id: str = deployment_id or _generated_deployment_id(created_at=created_at)
    if re.fullmatch(DEPLOYMENT_ID_PATTERN, resolved_deployment_id) is None:
        raise BackfillExecutionError(
            "Deployment ID must match YYYYMMDDTHHMMSSZ_<alphanumeric-suffix>"
        )
    return BackfillDeploymentIdentity(
        deployment_id=resolved_deployment_id,
        created_at=created_at,
    )


def _generated_deployment_id(*, created_at: str) -> str:
    timestamp: datetime = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:6]}"
