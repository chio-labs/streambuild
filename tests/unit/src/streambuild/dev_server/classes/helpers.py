import signal
import subprocess
import threading
from collections.abc import Iterator


class CancellingProcess:
    def __init__(self) -> None:
        self.signal_received: int | None = None
        self.terminated: bool = False
        self.killed: bool = False

    def poll(self) -> int | None:
        return None

    def send_signal(self, requested_signal: int) -> None:
        self.signal_received = requested_signal

    def wait(self, timeout: float = 0.0) -> int:
        raise subprocess.TimeoutExpired(cmd="stb build", timeout=timeout)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def expected_interrupt_signal() -> int:
    return signal.SIGINT


class PendingBuildOutput:
    def __init__(self) -> None:
        self.release: threading.Event = threading.Event()

    def __iter__(self) -> Iterator[str]:
        self.release.wait(timeout=5)
        return iter(())


class PendingBuildProcess:
    def __init__(self) -> None:
        self.stdout: PendingBuildOutput = PendingBuildOutput()
        self.poll_result: int | None = None

    def poll(self) -> int | None:
        return self.poll_result

    def wait(self, timeout: float | None = None) -> int:
        _ = self.stdout.release.wait(timeout=timeout)
        return 0

    def finish(self) -> None:
        self.poll_result = 0
        self.stdout.release.set()
