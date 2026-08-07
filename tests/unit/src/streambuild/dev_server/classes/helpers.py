import signal
import subprocess


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
