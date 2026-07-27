"""Build and publish one complete static compile target."""

from pathlib import Path

from streambuild.cli.compile._helpers.publication import publish_static_compile_artifacts
from streambuild.cli.compile._helpers.static_artifacts import build_static_compile_artifacts
from streambuild.cli.compile.models import StaticCompileArtifacts
from streambuild.compiler.pipeline.models import CompileAnalysis


def write_static_compile_target(*, analysis: CompileAnalysis, target_dir: Path) -> None:
    """Generate all static bytes before atomically replacing each owned path."""

    artifacts: StaticCompileArtifacts = build_static_compile_artifacts(analysis=analysis)
    publish_static_compile_artifacts(artifacts=artifacts, target_dir=target_dir)
