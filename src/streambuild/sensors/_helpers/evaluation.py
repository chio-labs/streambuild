"""Evaluate one sensor handler in isolation with providers and a timeout."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from streambuild.provider.classes.session import ProviderSession
from streambuild.provider.main.build_provider_session import build_provider_session
from streambuild.provider.main.invoke_with_providers import invoke_with_providers
from streambuild.provider.models import DiscoveredProvider
from streambuild.sensors.models import (
    LoadedSensor,
    PollingSensorResult,
    SensorEvaluation,
    SkipReason,
)
from streambuild.sensors.types import SensorTickStatus


def evaluate_sensor_handler(
    *,
    sensor: LoadedSensor,
    context: object,
    providers: tuple[DiscoveredProvider, ...],
) -> SensorEvaluation:
    """Run one handler on a worker thread; failures never escape the evaluation."""

    executor: ThreadPoolExecutor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix=f"streambuild-sensor-{sensor.name}"
    )
    try:
        future: Future[object] = executor.submit(
            _invoke, sensor=sensor, context=context, providers=providers
        )
        result: object = future.result(timeout=sensor.timeout_seconds)
    except FutureTimeoutError:
        return SensorEvaluation(
            status=SensorTickStatus.FAILED,
            error_message=(
                f"Sensor '{sensor.name}' timed out after {sensor.timeout_seconds} seconds"
            ),
        )
    except Exception as error:
        return SensorEvaluation(
            status=SensorTickStatus.FAILED,
            error_message=f"{type(error).__name__}: {error}",
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    if isinstance(result, SkipReason):
        return SensorEvaluation(status=SensorTickStatus.SKIPPED, skip_reason=result.reason)
    if isinstance(result, PollingSensorResult):
        return SensorEvaluation(status=SensorTickStatus.SUCCEEDED, cursor=result.cursor)
    return SensorEvaluation(status=SensorTickStatus.SUCCEEDED)


def _invoke(
    *,
    sensor: LoadedSensor,
    context: object,
    providers: tuple[DiscoveredProvider, ...],
) -> object:
    session: ProviderSession = build_provider_session(
        discovered_providers=providers, setup_context=context
    )
    with session:
        return invoke_with_providers(
            function=sensor.declaration.function,
            context=context,
            providers=session.providers,
        )
