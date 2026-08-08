"""Shared confirmation vocabulary for direct and virtual builds."""

import sys

from streambuild.cli.build.models import BuildCommandOptions, BuildProtectionRequirement
from streambuild.cli.entry.constants import AFFIRMATIVE_RESPONSES
from streambuild.compiler.compile.models import CompiledProject, LogicalResourceKey
from streambuild.compiler.discovery.models import PipelineProtection


def build_protection_requirements(
    *, compiled_project: CompiledProject, execution_model_keys: frozenset[LogicalResourceKey]
) -> tuple[BuildProtectionRequirement, ...]:
    """Return protected pipelines containing at least one executing model."""

    requirements: list[BuildProtectionRequirement] = []
    for compiled_pipeline in compiled_project.pipelines:
        protection: PipelineProtection | None = compiled_pipeline.pipeline.protection
        if protection is None or not any(
            model.key in execution_model_keys for model in compiled_pipeline.models
        ):
            continue
        requirements.append(
            BuildProtectionRequirement(
                pipeline_name=compiled_pipeline.pipeline.name,
                warning=protection.warning,
                confirmation=protection.confirmation,
            )
        )
    return tuple(requirements)


def confirm_build(
    *,
    options: BuildCommandOptions,
    plan_text: str,
    protection_requirements: tuple[BuildProtectionRequirement, ...] = (),
) -> bool:
    """Render the connected plan and apply the common build confirmation policy."""

    if not options.json_output and not options.events_output:
        print(plan_text)
    if protection_requirements:
        provided_confirmations: frozenset[str] = frozenset(options.confirmations)
        for requirement in protection_requirements:
            print(
                f"PROTECTED PIPELINE: {requirement.pipeline_name}\n{requirement.warning}",
                file=sys.stderr,
            )
            if requirement.confirmation in provided_confirmations:
                continue
            if options.auto_approve or options.json_output or options.events_output:
                print(
                    f"Confirmation required: rerun with --confirm {requirement.confirmation}",
                    file=sys.stderr,
                )
                return False
            entered: str = input(
                f"Type {requirement.confirmation} to build protected pipeline "
                f"'{requirement.pipeline_name}': "
            ).strip()
            if entered != requirement.confirmation:
                print("Protected pipeline confirmation did not match.", file=sys.stderr)
                return False
        return True
    if options.auto_approve:
        return True
    return input("Proceed with build? [y/N] ").strip().lower() in AFFIRMATIVE_RESPONSES
