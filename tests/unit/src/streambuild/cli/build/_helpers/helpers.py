from pathlib import Path

from streambuild.cli.build.models import BuildCommandOptions, BuildProtectionRequirement


def build_confirmation_options(
    *, auto_approve: bool, confirmations: tuple[str, ...]
) -> BuildCommandOptions:
    return BuildCommandOptions(
        pipelines_root=Path("pipelines"),
        database="analytics",
        metadata_database=None,
        selectors=(),
        json_output=False,
        verbose=False,
        auto_approve=auto_approve,
        confirmations=confirmations,
    )


def build_protection_requirement() -> tuple[BuildProtectionRequirement, ...]:
    return (
        BuildProtectionRequirement(
            pipeline_name="protected_prices",
            warning="Interrupts protected trading prices.",
            confirmation="DEPLOY_PROTECTED_PRICES",
        ),
    )
