/**
 * The single authoritative StreamBuild domain model.
 *
 * `main` (the SQLBuild Hub) re-declared mock shapes inline in six route files and
 * they diverged — node status was 'fresh'|'stale'|'warn'|'fail'|'source' in one
 * place and 'ok'|'fail'|'warn'|'stale'|'src' in another, needing a mapping layer.
 * Everything here is declared once and derived from there.
 *
 * Names mirror StreamBuild's own vocabulary so this file stays a faithful mirror
 * of `target/manifest.json` + `streambuild_dag.json` + the direct plan payload.
 * See .ai/streambuild_ui_plan.md §2.
 */

// ─── replay ──────────────────────────────────────────────────────────────────

/** Boundary modes. `landed_at` is managed-source only; `cursor` is adopted only. */
export type ReplayBoundaryMode = 'offsets' | 'timestamp' | 'landed_at' | 'cursor';

/** The five normalized replay column roles. */
export type ReplayRole = 'partition' | 'offset' | 'timestamp' | 'landed_at' | 'cursor';

export const REPLAY_COLUMN_BY_ROLE: Record<ReplayRole, string> = {
	partition: '_replay_partition',
	offset: '_replay_offset',
	timestamp: '_replay_timestamp',
	landed_at: '_replay_landed_at',
	cursor: '_replay_cursor'
};

/**
 * Why a model is or isn't a replay anchor. A model can anchor when it preserves
 * its source's required lineage, is non-aggregate, has no mutable side
 * reference, and doesn't set `replay_anchor never`.
 */
export type AnchorState = 'eligible' | 'aggregate' | 'mutable_ref' | 'never' | 'lineage_loss' | 'view';

export const ANCHOR_REASON: Record<AnchorState, string> = {
	eligible: 'Replay anchor — a replay can start here',
	aggregate: 'Not an anchor: aggregate model, replay predicates go on its input',
	mutable_ref: 'Not an anchor: has a mutable side reference',
	never: 'Not an anchor: MODEL() sets replay_anchor never',
	lineage_loss: 'Not an anchor: replay lineage columns are not projected through',
	view: 'Terminal views take no part in replay'
};

// ─── sources ─────────────────────────────────────────────────────────────────

/** `kafka` = StreamBuild owns the landing objects. `stream_table` = adopted, never mutated. */
export type SourceKind = 'kafka' | 'stream_table';

export type ManagedRelationKind = 'kafka_engine' | 'landing_mv' | 'landing_table';

export type ManagedRelation = {
	kind: ManagedRelationKind;
	name: string;
	/** Rendered DDL for this managed object, straight from the compiler. */
	ddl: string | null;
};

export type PartitionState = {
	partition: number;
	/** Highest offset present in the StreamBuild landing table. */
	offset: number | null;
	committedOffset: number | null;
	endOffset: number | null;
	kafkaLagMessages: number | null;
	newestEventAt: string;
};

export type SourceLiveState = {
	rowsPerSecond: number;
	/**
	 * Server-evaluated against the source's configured freshness policy
	 * (warn_after / error_after). null when no policy is configured.
	 */
	freshness: 'fresh' | 'lagging' | 'stalled' | null;
	/** Age of the newest landed row. This is not Kafka consumer lag. */
	lastArrivalSeconds: number | null;
	/** Broker high-water offset minus the consumer group's committed offset. */
	kafkaLagMessages: number | null;
	newestEventAt: string;
	/** Start of the retained extent — the floor of what any rebuild can reconstruct. */
	oldestEventAt: string;
	rows: number;
	partitions: PartitionState[];
	/** Recent throughput buckets, newest last. Drives the sparkline. */
	throughput: number[];
	/** The window the throughput buckets cover, from the server query. */
	throughputWindowSeconds: number | null;
};

export type Source = {
	name: string;
	kind: SourceKind;
	boundaryMode: ReplayBoundaryMode;
	/** The relation models actually read: `raw__<name>` when managed, `table_name` when adopted. */
	relationName: string;
	/** Empty for adopted sources — StreamBuild creates nothing. */
	managedRelations: ManagedRelation[];
	/** ClickHouse TTL expression on the landing table. null = retained forever. */
	ttl: string | null;
	/** Parsed from `ttl` for arithmetic. null = infinite retention = lossless rebuilds. */
	retentionDays: number | null;
	brokerList: string | null;
	topic: string | null;
	consumerGroup: string | null;
	format: string | null;
	settings: Record<string, string> | null;
	/** Adopted sources only: declared role → user column. */
	columnMapping: Partial<Record<ReplayRole, string>> | null;
	live: SourceLiveState;
};

// ─── models ──────────────────────────────────────────────────────────────────

/** `table` creates a table + the MV that writes it. `view` is a terminal query view. */
export type ModelKind = 'table' | 'view';

/** Typed graph edges. Exactly one `driving_input` per table model. */
export type RefType = 'driving_input' | 'reference' | 'mutable_reference';

export const REF_TYPE_LABEL: Record<RefType, string> = {
	driving_input: 'driving input',
	reference: 'reference',
	mutable_reference: 'mutable reference'
};

export type ModelRef = {
	/** Logical name — a source name or another model name. */
	name: string;
	type: RefType;
	alias: string | null;
	/** True when the ref resolves to a source rather than a model. */
	isSource: boolean;
};

export type Column = {
	name: string;
	type: string;
	/** Set when this column carries a normalized replay role. */
	replayRole: ReplayRole | null;
	description: string | null;
};

export type StorageSpec = {
	/** null for terminal views — storage fields are rejected on views. */
	engine: string | null;
	orderBy: string[];
	partitionBy: string | null;
	ttl: string | null;
	settings: Record<string, string> | null;
};

/**
 * How StreamBuild regards a live relation. `unmanaged` and `conflicted` mean a
 * build would touch something it doesn't own — the Plan page makes both loud.
 */
export type OwnershipState =
	| 'direct'
	| 'unmanaged'
	| 'conflicted'
	| 'absent'
	| 'virtual_environment';

export const OWNERSHIP_LABEL: Record<OwnershipState, string> = {
	direct: 'owned by StreamBuild (direct)',
	unmanaged: 'not owned by StreamBuild',
	conflicted: 'owned by another mode',
	absent: 'does not exist yet',
	virtual_environment: 'owned by a virtual environment'
};

/**
 * Freshness relative to the source, plus `drift` for code/warehouse mismatch.
 * `source` is used for source nodes on the graph.
 */
export type ModelStatus = 'fresh' | 'lagging' | 'stalled' | 'drift' | 'source';

export type ModelActivity = {
	state: 'moving' | 'idle' | 'stalled' | 'unknown';
	source: 'query_views_log' | 'part_log' | 'system_parts' | 'unavailable';
	sourceAvailable: boolean;
	approximate: boolean;
	lastTriggeredAt: string | null;
	lastWriteAt: string | null;
	rowsWritten: number;
	windowSeconds: number;
	detail: string;
};

export type SqlArtifacts = {
	/** The authored .sql file including its MODEL() header. */
	authored: string;
	/** Resolved SELECT after macro expansion and ref resolution. */
	compiled: string;
	tableDdl: string | null;
	mvDdl: string | null;
	viewDdl: string | null;
};

export type ModelLiveState = {
	rows: number;
	diskBytes: number;
	parts: number;
	newestRowAt: string | null;
	/** Start of the extent this table actually holds — may predate source retention. */
	oldestRowAt: string | null;
	lagSeconds: number | null;
	activity: ModelActivity;
	/** Live DDL matches compiled DDL. False = drift. */
	inSyncWithCompiled: boolean;
	/** Server-reported reasons the live warehouse diverges from compiled state. */
	driftReasons: string[];
	ownership: OwnershipState;
	/** From `streambuild_target_ownership.replay_coverage_json`. */
	recordedCoverage: { from: string; to: string } | null;
};

export type Model = {
	name: string;
	pipeline: string;
	kind: ModelKind;
	description: string | null;
	/** `tbl__<name>` / `view__<name>`, or an explicit `relation_name`. */
	relationName: string;
	/** `mv__<name>`. null for terminal views. */
	mvRelationName: string | null;
	/** Logical name of the single untyped driving input. null for terminal views. */
	drivingInput: string | null;
	refs: ModelRef[];
	columns: Column[];
	storage: StorageSpec;
	anchor: AnchorState;
	isAggregate: boolean;
	/** Set when MODEL() declares `replay_anchor never`. */
	anchorNever: boolean;
	sql: SqlArtifacts;
	live: ModelLiveState;
	status: ModelStatus;
};

// ─── pipelines ───────────────────────────────────────────────────────────────

export type PipelineMode = 'direct' | 'virtual';

export type Pipeline = {
	name: string;
	/** Per-pipeline build mode from `pipeline.toml [mode]`, else the project default. */
	mode: PipelineMode;
	/** null for a valid view-only pipeline. */
	sourceName: string | null;
	/** Inherited from the source. null when source-less. */
	boundaryMode: ReplayBoundaryMode | null;
	/** Model names, in no particular order — read the tree instead. */
	models: string[];
	/** From an optional `pipeline.toml [naming]`. */
	naming: { tablePrefix: string | null; viewPrefix: string | null } | null;
	/** Present when `pipeline.toml` declares `[protection]`. */
	protection: { warning: string; confirmation: string } | null;
	auditDefaults: {
		severity: Severity | null;
		cadenceSeconds: number | null;
		warmupSeconds: number | null;
	};
	directory: string;
};

// ─── checks ──────────────────────────────────────────────────────────────────

export type Severity = 'error' | 'warning';

export type CellValue = string | number | null;

export type QualityDriftReason =
	| 'binding_changed'
	| 'definition_changed'
	| 'execution_changed'
	| 'schedule_changed';

export type QualityIdentity = {
	bindingKey: string;
	definitionFingerprint: string;
	executionFingerprint: string;
};

export type AuditPolicy = {
	cadenceSeconds: number | null;
	warmupSeconds: number;
	scheduled: boolean;
};

export type AuditResult = {
	passed: boolean;
	failingRowCount: number;
	sampleColumns: string[];
	sampleRows: CellValue[][];
	checkedAt: string;
	driftReasons: QualityDriftReason[];
	deferredUntil?: string | null;
};

export type Audit = {
	name: string;
	file: string;
	severity: Severity;
	description: string | null;
	referencedModels: string[];
	/** True when instantiated from `audits/generic/` via a schema.yml entry. */
	generic: boolean;
	/** The generic definition it came from, when `generic`. */
	genericName: string | null;
	sql: string;
	identity: QualityIdentity;
	policy: AuditPolicy;
	result: AuditResult | null;
};

/** Results are a two-sided bag diff, which renders as expected-vs-actual. */
export type SqlTestTargetResult = {
	targetModelName: string;
	passed: boolean;
	columns: string[];
	missingRows: CellValue[][];
	unexpectedRows: CellValue[][];
};

export type SqlTestResult = {
	passed: boolean;
	/** One diff per compared target — multi-target tests produce several. */
	targets: SqlTestTargetResult[];
	checkedAt: string;
	errorMessage: string | null;
	driftReasons: QualityDriftReason[];
};

export type SqlTest = {
	name: string;
	file: string;
	/** Multi-target tests exist — they land under `tests/_chain_/`. */
	targets: string[];
	sql: string;
	identity: QualityIdentity;
	result: SqlTestResult | null;
};

// ─── macros ──────────────────────────────────────────────────────────────────

export type Macro = {
	name: string;
	file: string;
	signature: string;
	description: string | null;
};

// ─── project ─────────────────────────────────────────────────────────────────

export type Project = {
	name: string;
	target: string;
	database: string;
	adapter: string;
	connection: { host: string; port: number; username: string; secure: boolean };
	vars: Record<string, string | number | boolean>;
	naming: { tablePrefix: string; viewPrefix: string };
	defaults: {
		managedSourceTtl: string | null;
		modelTtl: string | null;
		kafkaBrokerList: string | null;
		audits: {
			severity: Severity | null;
			cadenceSeconds: number | null;
			warmupSeconds: number | null;
		};
	};
	/** Server clock at snapshot time — everything relative is computed from this. */
	capturedAt: string;
	sources: Source[];
	pipelines: Pipeline[];
	models: Model[];
	audits: Audit[];
	tests: SqlTest[];
	macros: Macro[];
};

// ─── graph (derived) ─────────────────────────────────────────────────────────

export type GraphMode = 'logical' | 'physical';

export type LogicalNodeType = 'source' | 'model' | 'view';

/** Physical node types map 1:1 onto real ClickHouse objects. */
export type PhysicalNodeType =
	| 'kafka_engine'
	| 'landing_mv'
	| 'landing_table'
	| 'adopted_table'
	| 'model_mv'
	| 'model_table'
	| 'model_view';

/** Why a physical relation exists in the warehouse, for the physical view. */
export type RelationDeploymentState = 'active' | 'staged' | 'orphaned';

export type NodeDeployment = {
	deploymentId: string;
	state: RelationDeploymentState;
};

export type GraphNode = {
	id: string;
	label: string;
	/** Logical name this node belongs to, for cross-linking back to detail pages. */
	logicalName: string;
	logicalType: LogicalNodeType;
	physicalType: PhysicalNodeType | null;
	status: ModelStatus;
	anchor: AnchorState | null;
	kindLabel: string;
	sublabel: string | null;
	rows: number | null;
	rowsPerSecond: number | null;
	failingChecks: number;
	warningChecks: number;
	totalChecks: number;
	drift: boolean;
	/** Set only for deployment-suffixed relations in the physical view. */
	deployment?: NodeDeployment | null;
};

export type GraphEdge = {
	id: string;
	source: string;
	target: string;
	type: RefType;
	/** Unknown remains a visible driver; only measured stalls lose the driving hue. */
	flowState: 'flowing' | 'stalled' | 'unknown';
};

export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

// ─── plan (derived) ──────────────────────────────────────────────────────────

/** A selector is a bare model name or `pipeline:<name>`. Nothing else parses. */
export type Selector = { kind: 'model' | 'pipeline'; name: string };

export type PlanEntryReason = 'selected' | 'downstream_of_selected' | 'all_models';

export type PlanSqlChangeStatus =
	| 'first_baseline'
	| 'query_changed'
	| 'no_query_change'
	| 'baseline_unavailable';

export type PlanSqlChange = {
	status: PlanSqlChangeStatus;
	unifiedDiff: string | null;
	warning: string | null;
};

export const PLAN_REASON_LABEL: Record<PlanEntryReason, string> = {
	selected: 'selected',
	downstream_of_selected: 'downstream of selection',
	all_models: 'all models'
};

export type PlanEntry = {
	modelName: string;
	pipeline: string;
	reason: PlanEntryReason;
	relationNames: string[];
	resourceKinds: ('table' | 'materialized_view' | 'view')[];
	ownership: { relation: string; ownership: OwnershipState }[];
	drivingInput: string | null;
	isReplayRoot: boolean;
	sqlChange: PlanSqlChange | null;
};

export type PlanAction = {
	relationName: string;
	action: 'drop' | 'create';
	modelName: string;
	resourceKind: 'table' | 'materialized_view' | 'view';
};

export type PlanReplayRoot = {
	modelName: string;
	drivingInputName: string;
	drivingInputRelationName: string;
	boundaryMode: ReplayBoundaryMode;
	replayColumns: Partial<Record<ReplayRole, string>>;
	propagatedModelNames: string[];
	hasAggregateSemantics: boolean;
	/**
	 * Rows the replay of this root will read, counted against the landing table
	 * with the same predicate the build uses. A count, not an estimate. null when
	 * the anchor table does not exist yet.
	 */
	rowsToReplay: number | null;
};

export type PlanWarning = {
	code: string;
	message: string;
	relatedModel: string | null;
};

export type PlanProtection = {
	pipelineName: string;
	warning: string;
	confirmation: string;
};

export type PlanPrerequisite = {
	name: string;
	type: 'source' | 'model';
	relationNames: string[];
	present: boolean;
	frameworkManaged: boolean;
};

export type ReplayWindow =
	| { mode: 'full' }
	| { mode: 'from'; startTime: string };

export type Plan = {
	adapter: string;
	database: string;
	/** What the user asked for. */
	userScope: Selector[];
	/** What will actually be rebuilt — always the full downstream closure. */
	entries: PlanEntry[];
	prerequisites: PlanPrerequisite[];
	teardown: PlanAction[];
	creation: PlanAction[];
	replayRoots: PlanReplayRoot[];
	warnings: PlanWarning[];
	protections: PlanProtection[];
	replayWindow: ReplayWindow;
	plannedAt: string;
	command: string;
};

// ─── reconstruction (derived) ────────────────────────────────────────────────

/**
 * Compares what a model table holds against what its source can still
 * reconstruct. `truncating` is a standing latent condition: the next rebuild
 * silently drops the overhang. The CLI never tells you this.
 */
export type ReconstructionState = 'matched' | 'truncating' | 'lossless' | 'unknown';

export type ReconstructionCoverage = {
	modelName: string;
	sourceName: string;
	state: ReconstructionState;
	heldFrom: string | null;
	retainedFrom: string | null;
	heldDays: number | null;
	retainedDays: number | null;
	/** Days of model history the source can no longer rebuild. */
	unreconstructableDays: number | null;
};

// ─── deployments ─────────────────────────────────────────────────────────────

export type DeploymentState =
	| 'active'
	| 'staged'
	| 'superseded'
	| 'incomplete'
	| 'metadata_missing'
	| 'physical_missing';

export type Deployment = {
	deploymentId: string;
	state: DeploymentState;
	createdAt: string | null;
	publishedAt: string | null;
	persistedStatus: string | null;
	rootNames: string[];
	physicalRelationNames: string[];
	activeBindingNames: string[];
	missingRelationNames: string[];
	modelCount: number;
	relationCount: number;
	rows: number;
	bytes: number;
};

export type DeploymentModel = {
	logicalName: string;
	stagedRelation: string;
	stagedRows: number;
	stagedBytes: number;
	liveRelation: string | null;
	liveDeploymentId: string | null;
	liveRows: number | null;
	isActive: boolean;
	isNew: boolean;
};

export type DeploymentPromotionPreview = {
	classification: 'initial_publish' | 'promotion';
	additions: {
		database: string;
		logicalName: string;
		physicalName: string;
	}[];
	replacements: {
		database: string;
		logicalName: string;
		fromPhysicalName: string;
		toPhysicalName: string;
	}[];
	removals: {
		database: string;
		logicalName: string;
		physicalName: string;
	}[];
};

export type DeploymentDetail = Deployment & {
	database: string;
	models: DeploymentModel[];
	promotionPreview: DeploymentPromotionPreview | null;
	wouldOrphan: { relationNames: string[]; relationCount: number; bytes: number };
};
