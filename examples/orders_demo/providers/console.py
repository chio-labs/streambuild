"""Local notification provider with no network side effects."""

from streambuild.providers import Provider


class ConsoleNotifier(Provider):
    """Print audit transitions to the StreamBuild process console."""

    def notify(self, message: str) -> None:
        print(f"[orders-demo] {message}", flush=True)  # noqa: T201 - intentional local output
