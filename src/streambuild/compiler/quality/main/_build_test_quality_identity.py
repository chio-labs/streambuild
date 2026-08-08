"""Build the stable identity of one compiled SQL test."""

from streambuild.compiler.quality._helpers.identity import build_identity, quality_node_name
from streambuild.compiler.quality.models import QualityNodeIdentity
from streambuild.compiler.quality.types import QualityNodeKind
from streambuild.compiler.sql_analysis.main._canonicalize_sql import canonicalize_sql
from streambuild.compiler.test_discovery.models import LoadedSqlTest
from streambuild.compiler.testing.models import SqlTestCase


def build_test_quality_identity(
    *, loaded_test: LoadedSqlTest, test_case: SqlTestCase, dialect: str
) -> QualityNodeIdentity:
    """Build authored-definition and assembled-execution identity for one SQL test."""

    node_name: str = quality_node_name(
        name=loaded_test.name,
        file_stem=loaded_test.file_path.stem,
    )
    binding_payload: dict[str, object] = {
        "assertion_names": sorted(assertion.name for assertion in test_case.assertion_cases),
        "expected_targets": sorted(target.target_model_name for target in test_case.target_cases),
        "mode": str(loaded_test.mode),
        "node_kind": QualityNodeKind.TEST,
        "node_name": node_name,
    }
    return build_identity(
        node_kind=QualityNodeKind.TEST,
        node_name=node_name,
        binding_payload=binding_payload,
        definition={
            "authored_ctes": [
                {
                    "name": cte.name,
                    "sql": canonicalize_sql(sql=cte.query, dialect=dialect),
                }
                for cte in loaded_test.authored_ctes
            ]
        },
        execution={"sql": canonicalize_sql(sql=test_case.query, dialect=dialect)},
    )
