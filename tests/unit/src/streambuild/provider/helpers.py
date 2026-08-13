from typing import ClassVar

from streambuild.providers import Provider

LIFECYCLE_LOG: list[str] = []


def drain_lifecycle_log() -> tuple[str, ...]:
    entries: tuple[str, ...] = tuple(LIFECYCLE_LOG)
    LIFECYCLE_LOG.clear()
    return entries


class QualitySlack(Provider):
    webhook_url: str = "https://hooks.example.invalid/quality"

    def setup(self, ctx: object) -> None:
        LIFECYCLE_LOG.append("setup:quality_slack")

    def teardown(self) -> None:
        LIFECYCLE_LOG.append("teardown:quality_slack")


class OpsSlack(Provider):
    webhook_url: str = "https://hooks.example.invalid/ops"

    def setup(self, ctx: object) -> None:
        LIFECYCLE_LOG.append("setup:ops_slack")

    def teardown(self) -> None:
        LIFECYCLE_LOG.append("teardown:ops_slack")


class ExplodingTeardown(Provider):
    def teardown(self) -> None:
        raise RuntimeError("socket already closed")


class BadName(Provider):
    provider_name: ClassVar[str | None] = "Not Valid"


class SlackRecorder:
    def __init__(self) -> None:
        self.seen: list[object] = []

    def __call__(self, ctx: object, quality_slack: QualitySlack) -> None:
        self.seen.append(quality_slack)


def handler_requiring_ops_slack(ctx: object, ops_slack: OpsSlack) -> None:
    del ops_slack
