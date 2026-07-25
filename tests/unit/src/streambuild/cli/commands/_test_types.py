from dataclasses import dataclass


@dataclass(frozen=True)
class CliMainTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliMainErrorTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliMainIntegrationTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliMainEnvResolutionTestCase:
    description: str
    argv: tuple[str, ...]
    env_vars: dict[str, str]
    expected_exit_code: int
    expected_kwargs: dict[str, object]


@dataclass(frozen=True)
class CliMainJsonFlagTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_json_output: bool


@dataclass(frozen=True)
class CliSelectorForwardingTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_selectors: tuple[str, ...]
    expected_full_refresh: bool


@dataclass(frozen=True)
class CliRenderingTestCase:
    description: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliExpectedErrorRenderingTestCase:
    description: str
    error_message: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliCommandErrorTestCase:
    description: str
    error_message: str
    expected_exit_code: int
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliJanitorApplyFlagTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_apply: bool


@dataclass(frozen=True)
class CliReconcileForwardingTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_selectors: tuple[str, ...]
    expected_apply: bool
    expected_json_output: bool


@dataclass(frozen=True)
class CliProjectDefaultsTestCase:
    description: str
    command_name: str
    expected_database: str


@dataclass(frozen=True)
class CliProjectConnectionResolutionTestCase:
    description: str
    expected_project_connection: tuple[str, int, str, str]


@dataclass(frozen=True)
class CliCompileArtifactsTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_written_files: tuple[str, ...]


@dataclass(frozen=True)
class CliAuditBackfillProjectContextTestCase:
    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_project_dir_name: str
    expected_pipelines_root_name: str
