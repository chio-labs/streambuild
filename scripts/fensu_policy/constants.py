"""Path and module constants for StreamBuild's Fensu policy."""

PRODUCT_SCOPE_NAME: str = "root"
COMPILER_PATH_PREFIX: tuple[str, ...] = ("src", "streambuild", "compiler")
SQL_ANALYSIS_PATH_PREFIX: tuple[str, ...] = (
    "src",
    "streambuild",
    "compiler",
    "sql_analysis",
)
CLICKHOUSE_ADAPTER_PATH_PREFIX: tuple[str, ...] = (
    "src",
    "streambuild",
    "adapters",
    "clickhouse",
)
ADAPTER_IMPLEMENTATION_MODULE_PREFIX: tuple[str, ...] = ("streambuild", "adapters")
CLICKHOUSE_DRIVER_ROOT_MODULE: str = "clickhouse_connect"
POLYGLOT_ROOT_MODULE: str = "polyglot_sql"
SQLGLOT_ROOT_MODULE: str = "sqlglot"
DYNAMIC_IMPORT_CALL_NAMES: tuple[str, ...] = ("__import__", "importlib.import_module")
RETIRED_CLICKHOUSE_MODULE_PREFIX: tuple[str, ...] = ("streambuild", "clickhouse")
RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX: tuple[str, ...] = (
    "streambuild",
    "integrations",
    "clickhouse",
)
WORKFLOW_GATEWAY_PATH: tuple[str, ...] = (
    "src",
    "streambuild",
    "executor",
    "workflow",
    "main",
    "_execute_warehouse_workflow.py",
)
ADAPTER_CONNECTION_MODULE_PARTS: tuple[str, ...] = (
    "streambuild",
    "adapter",
    "classes",
    "adapter_connection",
)
ADAPTER_CONNECTION_SYMBOL: str = "AdapterConnection"
CLICKHOUSE_CONNECTION_MODULE_PARTS: tuple[str, ...] = (
    "streambuild",
    "adapters",
    "clickhouse",
    "classes",
    "clickhouse_connection",
)
CLICKHOUSE_CONNECTION_PATH: tuple[str, ...] = (
    "src",
    "streambuild",
    "adapters",
    "clickhouse",
    "classes",
    "clickhouse_connection.py",
)
CLICKHOUSE_CONNECTION_SYMBOL: str = "ClickHouseConnection"
WORKFLOW_MODELS_MODULE_PARTS: tuple[str, ...] = (
    "streambuild",
    "executor",
    "workflow",
    "models",
)
BUILD_WORKFLOW_EXECUTION_PATH: tuple[str, ...] = (
    "src",
    "streambuild",
    "executor",
    "workflow",
    "main",
    "execute_build_workflow.py",
)
BUILD_WORKFLOW_PUBLICATION_PATH: tuple[str, ...] = (
    "src",
    "streambuild",
    "cli",
    "workflow_artifacts",
    "main",
    "_publish_build_workflow.py",
)
WORKFLOW_CONSUMER_PATHS: tuple[tuple[str, ...], ...] = (
    WORKFLOW_GATEWAY_PATH,
    BUILD_WORKFLOW_EXECUTION_PATH,
    BUILD_WORKFLOW_PUBLICATION_PATH,
    (
        "src",
        "streambuild",
        "cli",
        "workflow_artifacts",
        "_helpers",
        "build_publication.py",
    ),
)
WORKFLOW_ASSEMBLER_PATHS: tuple[tuple[str, ...], ...] = (
    ("src", "streambuild", "executor", "direct", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "backfill", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "population", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "promotion", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "repair", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "janitor", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "reconcile", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "destruction", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "observability", "_helpers", "workflow.py"),
    ("src", "streambuild", "executor", "auditing", "_helpers", "schedule_claim_workflow.py"),
    ("src", "streambuild", "sensors", "_helpers", "workflow.py"),
)
RETIRED_ADAPTER_MUTATION_METHODS: tuple[str, ...] = (
    "command",
    "insert_rows",
    "ensure_database",
    "realize_resource",
    "migrate_metadata_state",
    "persist_metadata_state",
    "execute_replay",
    "replace_stable_bindings",
    "cleanup_relations",
)
WORKFLOW_CONSUMER_PROHIBITED_CALLS: tuple[str, ...] = (
    "WarehouseStatement",
    "render_resource",
    "sorted",
    "reversed",
)
WORKFLOW_GATEWAY_CALL_NAME: str = "execute_workflow_sql"
BUILD_WORKFLOW_EXECUTION_FUNCTION: str = "execute_build_workflow"
BUILD_WORKFLOW_EXECUTION_PARAMETERS: tuple[str, ...] = (
    "published_workflow",
    "connection",
    "emitter",
)
PUBLISHED_WORKFLOW_CONSTRUCTOR_NAME: str = "PublishedBuildWorkflow"
WORKFLOW_STATEMENT_CONSTRUCTOR_NAME: str = "WarehouseStatement"
WORKFLOW_PLAN_CALL_PREFIX: str = "plan_"
WORKFLOW_RENDER_CALL_PREFIX: str = "render_"
WORKFLOW_TOPOLOGICAL_CALL_FRAGMENT: str = "topological"
ANNOTATED_ASSIGNMENT_CHILD_COUNT: int = 2
METHOD_REFERENCE_MINIMUM_PARTS: int = 2
FUNCTION_DEFINITION_SYNTAX_KINDS: tuple[str, ...] = (
    "FunctionDef",
    "AsyncFunctionDef",
)
ADAPTER_CLASS_RECEIVER_NAMES: tuple[str, ...] = ("self", "cls")
OBSERVABILITY_AUTHORITY_ALLOWED_PATH_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("src", "streambuild", "adapter"),
    ("src", "streambuild", "adapters"),
    ("src", "streambuild", "executor", "observability"),
    ("src", "streambuild", "executor", "workflow", "main", "_execute_observation_workflow.py"),
    ("src", "streambuild", "quality"),
    ("src", "streambuild", "dev_server"),
    ("src", "streambuild", "sensors"),
    ("src", "streambuild", "events"),
)
QUALITY_MODULE_PREFIX: tuple[str, ...] = ("streambuild", "quality")
OBSERVABILITY_QUERY_CALL_NAMES: frozenset[str] = frozenset({"render_latest_node_status_query"})
OBSERVABILITY_TABLE_CONSTANT_NAMES: frozenset[str] = frozenset(
    {
        "METADATA_INVOCATIONS_TABLE_NAME",
        "METADATA_NODE_RESULTS_TABLE_NAME",
        "METADATA_RUN_EVENTS_TABLE_NAME",
        "METADATA_SENSOR_CHECKPOINTS_TABLE_NAME",
        "METADATA_SENSOR_TICKS_TABLE_NAME",
        "METADATA_SENSOR_STEPS_TABLE_NAME",
        "METADATA_SENSOR_OVERRIDES_TABLE_NAME",
        "METADATA_SENSOR_LEASES_TABLE_NAME",
    }
)
OBSERVABILITY_TABLE_NAMES: frozenset[str] = frozenset(
    {
        "_streambuild_invocations",
        "_streambuild_node_results",
        "_streambuild_run_events",
        "_streambuild_sensor_checkpoints",
        "_streambuild_sensor_ticks",
        "_streambuild_sensor_steps",
        "_streambuild_sensor_overrides",
        "_streambuild_sensor_leases",
    }
)
EVENT_CATALOG_PATH_PREFIX: tuple[str, ...] = ("src", "streambuild", "events")
EVENT_CONSTRUCTION_CALL_NAMES: frozenset[str] = frozenset({"AuditCompleted(", "RunCompleted("})
