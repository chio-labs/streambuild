"""Build the StreamBuild-native logical DAG JSON artifact."""

from streambuild.compiler.dag._helpers.artifact import build_dag_artifact, format_dag_artifact
from streambuild.compiler.graph.models import ProjectGraph
from streambuild.compiler.macros.models import MacroRegistry


def build_dag_json(*, graph: ProjectGraph, macro_registry: MacroRegistry) -> str:
    """Return deterministic JSON for one compiled logical project graph."""

    return format_dag_artifact(
        artifact=build_dag_artifact(graph=graph, macro_registry=macro_registry)
    )
