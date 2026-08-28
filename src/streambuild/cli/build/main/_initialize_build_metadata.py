"""Initialize metadata and publish the complete compiled project manifest."""

import os

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build.constants import STREAMBUILD_TOOL_VERSION
from streambuild.compiler.manifest.main.build_manifest import build_manifest
from streambuild.compiler.manifest.main.resolve_manifest_project_identity import (
    resolve_manifest_project_identity,
)
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.observability.constants import PROJECT_REVISION_ENV_VAR
from streambuild.executor.observability.main.initialize_observability import (
    initialize_observability,
)
from streambuild.executor.observability.main.publish_manifest import publish_manifest


def initialize_build_metadata(
    *,
    analysis: CompileAnalysis,
    invocation_id: str,
    target_database: str,
    metadata_database: str,
    connection: AdapterConnection,
) -> None:
    """Migrate metadata then append one full-project manifest."""

    initialize_observability(connection=connection, database=metadata_database)
    publish_manifest(
        connection=connection,
        database=metadata_database,
        manifest=build_manifest(
            analysis=analysis,
            invocation_id=invocation_id,
            project_identity=resolve_manifest_project_identity(analysis=analysis),
            target_database=target_database,
            tool_version=STREAMBUILD_TOOL_VERSION,
            project_revision=os.environ.get(PROJECT_REVISION_ENV_VAR),
        ),
    )
