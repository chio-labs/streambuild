"""Closed event vocabulary derived from persisted observations."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from streambuild.events.models import AuditCompleted, RunCompleted

type SensorEvent = AuditCompleted | RunCompleted


class AuditTransition(StrEnum):
    """Status transition computed against the previous result for one binding."""

    NEW_FAILURE = "new_failure"
    STILL_FAILING = "still_failing"
    RECOVERED = "recovered"
    STILL_PASSING = "still_passing"


class ObservedCommand(StrEnum):
    """Closed catalog of commands recorded as terminal invocations."""

    AUDIT = "audit"
    TEST = "test"
    BUILD = "build"
    DEPLOYMENT_PROMOTE = "deployment promote"
    JANITOR = "janitor"
