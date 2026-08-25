from dataclasses import dataclass


@dataclass(frozen=True)
class ExactCompileTargetTestCase:
    description: str
    expected_relative_files: tuple[str, ...]
    expected_forbidden_path: str


@dataclass(frozen=True)
class ViewCompileTargetTestCase:
    description: str
    expected_relative_files: tuple[str, ...]
    expected_resource_kind: str
    expected_relation_name: str


@dataclass(frozen=True)
class AdoptedCompileTargetTestCase:
    description: str
    expected_relation_name: str
    expected_source_resource_count: int
    expected_forbidden_workflow_path: str


@dataclass(frozen=True)
class DerivedSourceManifestTestCase:
    description: str
    expected_name: str
    expected_origin: str
    expected_macro_name: str


@dataclass(frozen=True)
class SourceRetentionManifestTestCase:
    description: str
    expected_ttl: str
    expected_origin: str
    expected_duration_seconds: int


@dataclass(frozen=True)
class StaticReplacementTestCase:
    description: str
    stale_relative_paths: tuple[str, ...]
    runtime_relative_path: str
    runtime_contents: bytes
    legacy_relative_path: str
    expected_exit_code: int


@dataclass(frozen=True)
class CompileGenerationFailureTestCase:
    description: str
    expected_error_fragment: str
    expected_snapshot_preserved: bool


@dataclass(frozen=True)
class CompileArtifactIdentityTestCase:
    description: str
    expected_manifest_sources: tuple[str, ...]
    expected_manifest_models: tuple[str, ...]
    expected_dag_node_ids: tuple[str, ...]
    expected_edge: tuple[str, str, str]


@dataclass(frozen=True)
class CompileDiagnosticOutputTestCase:
    description: str
    expected_exit_code: int
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SqlTestArtifactPathTestCase:
    description: str
    test_name: str
    target_names: tuple[str, ...]
    expected_static_path: str
    expected_runtime_path: str


@dataclass(frozen=True)
class AuditArtifactPathTestCase:
    description: str
    project_dir: str
    audit_file_path: str
    audit_name: str
    expected_path: str


@dataclass(frozen=True)
class UnsafeArtifactPathTestCase:
    description: str
    unsafe_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class DuplicateArtifactPathTestCase:
    description: str
    duplicate_path: str
    expected_error_fragment: str


@dataclass(frozen=True)
class CompileCheckArtifactsTestCase:
    description: str
    expected_test_path: str
    expected_audit_path: str
    expected_test_target: str
    expected_audit_model: str


@dataclass(frozen=True)
class EmptyCompileTargetTestCase:
    description: str
    expected_relative_files: tuple[str, ...]
    expected_pipeline_count: int
    expected_model_count: int


@dataclass(frozen=True)
class SourceSecretRedactionTestCase:
    description: str
    broker_secret: str
    setting_secret: str
    expected_placeholder: str


@dataclass(frozen=True)
class MultiTargetTestSqlTestCase:
    description: str
    target_names: tuple[str, ...]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PublicationRollbackTestCase:
    description: str
    failing_replace_call: int
    expected_error_fragment: str
    expected_snapshot_preserved: bool


@dataclass(frozen=True)
class RemovedStaticInputsTestCase:
    description: str
    removed_relative_inputs: tuple[str, ...]
    expected_removed_artifacts: tuple[str, ...]
    expected_removed_manifest_names: tuple[str, ...]
    expected_removed_dag_node_ids: tuple[str, ...]
