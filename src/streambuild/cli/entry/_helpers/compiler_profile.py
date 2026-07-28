"""Build the connection-free compiler view of a resolved adapter."""

from streambuild.adapter.classes.adapter import Adapter
from streambuild.compiler.compile.models import (
    CompilerAdapterProfile,
    CompilerExpressionInferenceProfile,
    CompilerTargetMetadata,
)


def build_compiler_adapter_profile(adapter: Adapter) -> CompilerAdapterProfile:
    """Capture compiler-facing adapter behavior without opening a warehouse connection."""

    return CompilerAdapterProfile(
        identity=adapter.identity,
        sql_analysis_dialect=adapter.sql_analysis_dialect,
        type_inference_profile=CompilerExpressionInferenceProfile(
            sql_analysis_dialect=adapter.sql_analysis_dialect,
        ),
        target_metadata=CompilerTargetMetadata(
            default_database=adapter.default_database,
            default_schema=adapter.default_schema,
        ),
        realize_source=adapter.realize_source,
        model_relation_name=adapter.model_relation_name,
        realize_model=adapter.realize_model,
        render_resource=adapter.render_resource,
        render_set_difference_comparison=adapter.render_set_difference_comparison,
    )
