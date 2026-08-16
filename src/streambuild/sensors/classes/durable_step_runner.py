"""Durable steps memoizing side-effect results per (sensor, event, key)."""

from __future__ import annotations

import json
from collections.abc import Callable

from streambuild.sensors.exceptions import SensorStepError
from streambuild.sensors.models import StepMarker
from streambuild.sensors.types import SensorStepStore, SensorTickStatus, StepPolicy


class DurableStepRunner:
    """At-least-once and at-most-once durable steps over a persisted store."""

    def __init__(self, *, store: SensorStepStore) -> None:
        self._store: SensorStepStore = store

    def run(
        self,
        key: str,
        fn: Callable[[], object],
        policy: StepPolicy = StepPolicy.AT_LEAST_ONCE,
    ) -> object:
        """Run one durable step, memoizing its JSON-serializable return value."""

        existing: StepMarker | None = self._store.read_step(step_key=key)
        if existing is not None and existing.status == SensorTickStatus.SUCCEEDED:
            return _decode_result(step_key=key, result_json=existing.result_json)
        if policy is StepPolicy.AT_MOST_ONCE:
            return self._run_at_most_once(key=key, fn=fn, existing=existing)
        return self._run_at_least_once(key=key, fn=fn, existing=existing)

    def _run_at_least_once(
        self, *, key: str, fn: Callable[[], object], existing: StepMarker | None
    ) -> object:
        attempt: int = (existing.attempt if existing is not None else 0) + 1
        value: object = fn()
        self._store.record_step(
            step_key=key,
            policy=StepPolicy.AT_LEAST_ONCE,
            status=SensorTickStatus.SUCCEEDED,
            attempt=attempt,
            result_json=_encode_result(step_key=key, value=value),
            error_message=None,
        )
        return value

    def _run_at_most_once(
        self, *, key: str, fn: Callable[[], object], existing: StepMarker | None
    ) -> object:
        if existing is not None:
            raise SensorStepError(
                f"Step '{key}' was already attempted under at-most-once policy and "
                "produced no memoized result"
            )
        self._store.record_step(
            step_key=key,
            policy=StepPolicy.AT_MOST_ONCE,
            status=SensorTickStatus.STARTED,
            attempt=1,
            result_json=None,
            error_message=None,
        )
        try:
            value: object = fn()
        except Exception as error:
            self._store.record_step(
                step_key=key,
                policy=StepPolicy.AT_MOST_ONCE,
                status=SensorTickStatus.FAILED,
                attempt=1,
                result_json=None,
                error_message=str(error),
            )
            raise
        self._store.record_step(
            step_key=key,
            policy=StepPolicy.AT_MOST_ONCE,
            status=SensorTickStatus.SUCCEEDED,
            attempt=1,
            result_json=_encode_result(step_key=key, value=value),
            error_message=None,
        )
        return value


def _encode_result(*, step_key: str, value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise SensorStepError(
            f"Step '{step_key}' returned a value that is not JSON-serializable: {error}"
        ) from error


def _decode_result(*, step_key: str, result_json: str | None) -> object:
    if result_json is None:
        raise SensorStepError(f"Step '{step_key}' succeeded without a memoized result")
    return json.loads(result_json)
