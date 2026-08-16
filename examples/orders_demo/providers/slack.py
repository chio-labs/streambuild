"""Providers resolve their settings from the environment via pydantic-settings."""

from pydantic import SecretStr

from streambuild.providers import Provider


class QualitySlack(Provider):
    """Post quality alerts to Slack; injected into sensors as `quality_slack`.

    Set QUALITY_SLACK_WEBHOOK_URL in the environment (or a .env loader) to
    override the placeholder; secrets never live in streambuild_project.toml.
    """

    webhook_url: SecretStr = SecretStr("https://hooks.slack.example/services/demo")

    def send(self, message: str) -> None:
        """Deliver one message; the demo provider only prints it."""

        print(f"[quality-slack] {message}")  # noqa: T201 - demo side effect
