"""Single-use in-memory storage for reviewed destruction plans."""

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock

from streambuild.executor.destruction.classes.stored_destruction_plan import (
    StoredDestructionPlan,
)
from streambuild.executor.destruction.exceptions import (
    DestructionChallengeError,
    DestructionPlanExpiredError,
    DestructionPlanNotFoundError,
    DestructionPlanNotReviewedError,
    DestructionValidationError,
)
from streambuild.executor.destruction.models import DestructionPlan


class InMemoryDestructionPlanStore:
    """Thread-safe, process-local storage with mandatory review and challenge gates."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._plans: dict[str, StoredDestructionPlan] = {}
        self._lock = Lock()

    def save(self, *, plan: DestructionPlan, actor: str) -> None:
        with self._lock:
            if plan.plan_id in self._plans:
                raise DestructionValidationError(
                    f"Destruction plan {plan.plan_id!r} already exists"
                )
            if not actor:
                raise DestructionValidationError("Destruction plan actor must not be empty")
            self._plans[plan.plan_id] = StoredDestructionPlan(plan=plan, actor=actor)

    def get(self, *, plan_id: str, actor: str) -> DestructionPlan:
        with self._lock:
            return self._require_actor(
                stored=self._require_current(plan_id=plan_id),
                actor=actor,
            ).plan

    def mark_reviewed(self, *, plan_id: str, actor: str) -> datetime:
        with self._lock:
            stored: StoredDestructionPlan = self._require_actor(
                stored=self._require_current(plan_id=plan_id),
                actor=actor,
            )
            reviewed_at: datetime = self._clock()
            stored.reviewed_at = reviewed_at
            return reviewed_at

    def reviewed_at(self, *, plan_id: str, actor: str) -> datetime:
        with self._lock:
            stored: StoredDestructionPlan = self._require_actor(
                stored=self._require_current(plan_id=plan_id),
                actor=actor,
            )
            if stored.reviewed_at is None:
                raise DestructionPlanNotReviewedError(
                    f"Destruction plan {plan_id!r} has not been reviewed"
                )
            return stored.reviewed_at

    def consume(
        self,
        *,
        plan_id: str,
        challenge_responses: tuple[str, ...],
        actor: str,
    ) -> DestructionPlan:
        with self._lock:
            stored: StoredDestructionPlan = self._require_actor(
                stored=self._require_current(plan_id=plan_id),
                actor=actor,
            )
            if stored.reviewed_at is None:
                raise DestructionPlanNotReviewedError(
                    f"Destruction plan {plan_id!r} has not been reviewed"
                )
            if challenge_responses != stored.plan.challenges:
                raise DestructionChallengeError(
                    "Challenge responses must exactly match the frozen plan in order"
                )
            del self._plans[plan_id]
            return stored.plan

    def _require_actor(
        self,
        *,
        stored: StoredDestructionPlan,
        actor: str,
    ) -> StoredDestructionPlan:
        if stored.actor != actor:
            raise DestructionPlanNotFoundError("Destruction plan was not found for this actor")
        return stored

    def _require_current(self, *, plan_id: str) -> StoredDestructionPlan:
        stored: StoredDestructionPlan | None = self._plans.get(plan_id)
        if stored is None:
            raise DestructionPlanNotFoundError(f"Destruction plan {plan_id!r} was not found")
        if self._clock() >= stored.plan.expires_at:
            del self._plans[plan_id]
            raise DestructionPlanExpiredError(f"Destruction plan {plan_id!r} has expired")
        return stored
