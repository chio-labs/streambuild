/**
 * Maps dev-server payloads onto the UI domain model.
 *
 * The server payloads were designed against these types, so most of this is
 * mechanical renaming plus the handful of derivations that are cheaper client
 * side (replay roles from column names and macro signatures).
 */

import type {
	AnchorState,
	Audit,
	CellValue,
	Column,
	Model,
	ModelStatus,
	PartitionState,
	Pipeline,
	Plan,
	PlanSqlChangeStatus,
	Project,
	ReplayRole,
	Source,
	SqlTest
} from '$lib/domain/types';
import type { CheckStatusRecord } from '$lib/api';

type Payload = Record<string, unknown>;

const REPLAY_ROLE_BY_COLUMN: Record<string, ReplayRole> = {
	_replay_partition: 'partition',
	_replay_offset: 'offset',
	_replay_timestamp: 'timestamp',
	_replay_landed_at: 'landed_at',
	_replay_cursor: 'cursor'
};

export function projectFromServer(definitions: Payload, state: Payload): Project {
	const header = definitions.project as Payload;
	const connection = (header.connection ?? {}) as Record<string, unknown>;
	const naming = (header.naming ?? {}) as Payload;
	const defaults = (header.defaults ?? {}) as Payload;
	const auditDefaults = (defaults.audits ?? {}) as Payload;
	const models = (definitions.models as Payload[]).map((model) =>
		modelFromServer(model, stateFor(state, 'models', model.name as string))
	);
	return {
		name: (header.name as string) ?? 'project',
		target: (header.target as string) ?? '',
		database: (header.database as string) ?? '',
		adapter: (header.adapter as string) ?? 'clickhouse',
		connection: {
			host: String(connection.host ?? ''),
			port: Number(connection.port ?? 0),
			username: String(connection.username ?? ''),
			secure: Boolean(connection.secure ?? false)
		},
		vars: (header.vars ?? {}) as Project['vars'],
		naming: {
			tablePrefix: (naming.tablePrefix as string) ?? 'tbl__',
			viewPrefix: (naming.viewPrefix as string) ?? 'view__'
		},
		defaults: {
			managedSourceTtl: (defaults.managedSourceTtl as string | null) ?? null,
			modelTtl: (defaults.modelTtl as string | null) ?? null,
			kafkaBrokerList: (defaults.kafkaBrokerList as string | null) ?? null,
			audits: {
				severity: (auditDefaults.severity as Project['defaults']['audits']['severity']) ?? null,
				cadenceSeconds: (auditDefaults.cadenceSeconds as number | null) ?? null,
				warmupSeconds: (auditDefaults.warmupSeconds as number | null) ?? null
			}
		},
		capturedAt: (state.capturedAt as string) ?? new Date().toISOString(),
		sources: (definitions.sources as Payload[]).map((source) =>
			sourceFromServer(source, stateFor(state, 'sources', source.name as string))
		),
		pipelines: (definitions.pipelines as Payload[]).map(pipelineFromServer),
		models,
		audits: (definitions.audits as Payload[]).map(auditFromServer),
		tests: (definitions.tests as Payload[]).map(testFromServer),
		macros: (definitions.macros as Payload[]).map((macro) => ({
			name: macro.name as string,
			file: macro.file as string,
			signature: signatureFromSource(macro.source as string, macro.name as string),
			description: (macro.description as string | null) ?? null
		}))
	};
}

function stateFor(state: Payload, section: string, name: string): Payload {
	const bucket = (state[section] ?? {}) as Record<string, Payload>;
	return bucket[name] ?? {};
}

function sourceFromServer(source: Payload, live: Payload): Source {
	const kafka = (source.kafka ?? null) as Payload | null;
	const throughput = (live.throughput ?? null) as Payload | null;
	const buckets = (throughput?.buckets ?? []) as number[];
	return {
		name: source.name as string,
		kind: source.kind === 'kafka' ? 'kafka' : 'stream_table',
		boundaryMode: source.boundaryMode as Source['boundaryMode'],
		relationName: source.relationName as string,
		managedRelations: ((source.managedRelations ?? []) as Payload[]).map((relation) => ({
			kind: relation.kind as Source['managedRelations'][number]['kind'],
			name: relation.name as string,
			ddl: (relation.ddl as string | null) ?? null
		})),
		ttl: (source.ttl as string | null) ?? null,
		retentionDays: retentionDaysFromTtl((source.ttl as string | null) ?? null),
		brokerList: (kafka?.brokerList as string) ?? null,
		topic: (kafka?.topic as string) ?? null,
		consumerGroup: (kafka?.consumerGroup as string) ?? null,
		format: (kafka?.format as string) ?? null,
		settings: (kafka?.settings as Record<string, string> | null) ?? null,
		columnMapping: (source.columnMapping as Source['columnMapping']) ?? null,
		live: {
			rowsPerSecond: (live.rowsPerSecond as number) ?? 0,
			freshness: (live.freshness as Source['live']['freshness']) ?? null,
			lastArrivalSeconds: (live.lastArrivalSeconds as number | null) ?? null,
			kafkaLagMessages: (live.kafkaLagMessages as number | null) ?? null,
			newestEventAt: (live.newestEventAt as string) ?? '',
			oldestEventAt: (live.oldestEventAt as string) ?? '',
			rows: (live.rows as number) ?? 0,
			partitions: ((live.partitions ?? []) as Payload[]).map(partitionFromServer),
			throughput: buckets,
			throughputWindowSeconds: (throughput?.windowSeconds as number | null) ?? null
		}
	};
}

function partitionFromServer(partition: Payload): PartitionState {
	const newest = (partition.newestEventAt as string) ?? '';
	return {
		partition: partition.partition as number,
		offset: (partition.maxOffset as number | null) ?? null,
		committedOffset: (partition.committedOffset as number | null) ?? null,
		endOffset: (partition.endOffset as number | null) ?? null,
		kafkaLagMessages: (partition.kafkaLagMessages as number | null) ?? null,
		newestEventAt: newest
	};
}

function pipelineFromServer(pipeline: Payload): Pipeline {
	const naming = (pipeline.naming ?? {}) as Payload;
	const protection = (pipeline.protection ?? null) as Payload | null;
	const auditDefaults = (pipeline.auditDefaults ?? {}) as Payload;
	return {
		name: pipeline.name as string,
		sourceName: (pipeline.sourceName as string | null) ?? null,
		boundaryMode: (pipeline.boundaryMode as Pipeline['boundaryMode']) ?? null,
		models: (pipeline.models as string[]) ?? [],
		naming: {
			tablePrefix: (naming.tablePrefix as string | null) ?? null,
			viewPrefix: (naming.viewPrefix as string | null) ?? null
		},
		protection:
			protection === null
				? null
				: {
						warning: (protection.warning as string) ?? '',
						confirmation: (protection.confirmation as string) ?? ''
					},
		auditDefaults: {
			severity: (auditDefaults.severity as Pipeline['auditDefaults']['severity']) ?? null,
			cadenceSeconds: (auditDefaults.cadenceSeconds as number | null) ?? null,
			warmupSeconds: (auditDefaults.warmupSeconds as number | null) ?? null
		},
		directory: (pipeline.directory as string) ?? ''
	};
}

function modelFromServer(model: Payload, live: Payload): Model {
	const sql = (model.sql ?? {}) as Payload;
	const ddl = (sql.ddl ?? {}) as Payload;
	const storage = (model.storage ?? null) as Payload | null;
	const anchor = model.anchor as AnchorState;
	const freshness = (live.freshness as string | null) ?? null;
	const drift = Boolean(live.drift ?? false);
	return {
		name: model.name as string,
		pipeline: model.pipeline as string,
		kind: model.kind === 'view' ? 'view' : 'table',
		description: (model.description as string | null) ?? null,
		relationName: model.relationName as string,
		mvRelationName: (model.mvRelationName as string | null) ?? null,
		drivingInput: (model.drivingInput as string | null) ?? null,
		refs: ((model.refs ?? []) as Payload[]).map((ref) => ({
			name: ref.name as string,
			type: ref.type as Model['refs'][number]['type'],
			alias: null,
			isSource: Boolean(ref.isSource)
		})),
		columns: ((model.columns ?? []) as Payload[]).map(columnFromServer),
		storage: {
			engine: (storage?.engine as string) ?? null,
			orderBy: (storage?.orderBy as string[]) ?? [],
			partitionBy: (storage?.partitionBy as string | null) ?? null,
			ttl: (storage?.ttl as string | null) ?? null,
			settings: (storage?.settings as Record<string, string> | null) ?? null
		},
		anchor,
		isAggregate: Boolean(model.isAggregate),
		anchorNever: anchor === 'never',
		sql: {
			authored: (sql.authored as string) ?? '',
			compiled: (sql.compiled as string) ?? '',
			tableDdl: (ddl.table as string | null) ?? null,
			mvDdl: (ddl.materializedView as string | null) ?? null,
			viewDdl: (ddl.view as string | null) ?? null
		},
		live: {
			rows: (live.rows as number) ?? 0,
			diskBytes: (live.diskBytes as number) ?? 0,
			parts: (live.parts as number) ?? 0,
			newestRowAt: (live.newestRowAt as string | null) ?? null,
			oldestRowAt: (live.oldestRowAt as string | null) ?? null,
			lagSeconds: (live.lagSeconds as number | null) ?? null,
			inSyncWithCompiled: !drift,
			driftReasons: (live.driftReasons as string[]) ?? [],
			ownership: ((live.ownership as string) ?? 'absent') as Model['live']['ownership'],
			recordedCoverage: (live.recordedCoverage as Model['live']['recordedCoverage']) ?? null
		},
		status: statusFromState(freshness, drift)
	};
}

function statusFromState(freshness: string | null, drift: boolean): ModelStatus {
	if (drift) return 'drift';
	if (freshness === 'lagging' || freshness === 'stalled') return freshness;
	return 'fresh';
}

function columnFromServer(column: Payload): Column {
	const name = column.name as string;
	return {
		name,
		type: column.type as string,
		replayRole: REPLAY_ROLE_BY_COLUMN[name] ?? null,
		description: (column.description as string | null) ?? null
	};
}

function auditFromServer(audit: Payload): Audit {
	const genericName = (audit.genericName as string | null) ?? null;
	const identity = audit.identity as Payload;
	const policy = audit.policy as Payload;
	return {
		name: audit.name as string,
		file: (audit.file as string) ?? '',
		severity: (audit.severity as Audit['severity']) ?? 'error',
		description: (audit.description as string | null) ?? null,
		referencedModels: (audit.referencedModels as string[]) ?? [],
		generic: genericName !== null,
		genericName,
		sql: (audit.sql as string) ?? '',
		identity: {
			bindingKey: identity.bindingKey as string,
			definitionFingerprint: identity.definitionFingerprint as string,
			executionFingerprint: identity.executionFingerprint as string
		},
		policy: {
			cadenceSeconds: (policy.cadenceSeconds as number | null) ?? null,
			warmupSeconds: Number(policy.warmupSeconds ?? 0),
			scheduled: Boolean(policy.scheduled)
		},
		result: null
	};
}

function testFromServer(test: Payload): SqlTest {
	const identity = test.identity as Payload;
	return {
		name: test.name as string,
		file: (test.file as string) ?? '',
		targets: (test.targets as string[]) ?? [],
		sql: (test.sql as string) ?? '',
		identity: {
			bindingKey: identity.bindingKey as string,
			definitionFingerprint: identity.definitionFingerprint as string,
			executionFingerprint: identity.executionFingerprint as string
		},
		result: null
	};
}

export function planFromServer(payload: Payload, adapter: string): Plan {
	return {
		adapter,
		database: (payload.database as string) ?? '',
		userScope: ((payload.userScope as string[]) ?? []).map(parseUserScope),
		entries: ((payload.entries as Payload[]) ?? []).map((entry) => ({
			modelName: entry.modelName as string,
			pipeline: (entry.pipeline as string) ?? '',
			reason: entry.reason as Plan['entries'][number]['reason'],
			relationNames: (entry.relationNames as string[]) ?? [],
			resourceKinds: (entry.resourceKinds as Plan['entries'][number]['resourceKinds']) ?? [],
			ownership: (entry.ownership as Plan['entries'][number]['ownership']) ?? [],
			drivingInput: (entry.drivingInput as string | null) ?? null,
			isReplayRoot: Boolean(entry.isReplayRoot),
			sqlChange: sqlChangeFromServer((entry.sqlChange as Payload | null) ?? null)
		})),
		prerequisites: ((payload.prerequisites as Payload[]) ?? []).map((item) => ({
			name: item.name as string,
			type: item.type === 'source' ? 'source' : 'model',
			relationNames: (item.relationNames as string[]) ?? [],
			present: Boolean(item.present),
			frameworkManaged: Boolean(item.frameworkManaged)
		})),
		teardown: ((payload.teardown as Payload[]) ?? []).map(operationFromServer),
		creation: ((payload.creation as Payload[]) ?? []).map(operationFromServer),
		replayRoots: ((payload.replayRoots as Payload[]) ?? []).map((root) => ({
			modelName: root.modelName as string,
			drivingInputName: (root.drivingInputName as string) ?? '',
			drivingInputRelationName: (root.drivingInputRelationName as string) ?? '',
			boundaryMode: root.boundaryMode as Plan['replayRoots'][number]['boundaryMode'],
			replayColumns: (root.replayColumns as Plan['replayRoots'][number]['replayColumns']) ?? {},
			propagatedModelNames: (root.propagatedModelNames as string[]) ?? [],
			hasAggregateSemantics: Boolean(root.hasAggregateSemantics),
			rowsToReplay: (root.rowsToReplay as number | null) ?? null
		})),
		warnings: ((payload.warnings as Payload[]) ?? []).map((warning) => ({
			code: (warning.code as string) ?? '',
			message: (warning.message as string) ?? '',
			relatedModel: null
		})),
		protections: ((payload.protections as Payload[]) ?? []).map((protection) => ({
			pipelineName: (protection.pipelineName as string) ?? '',
			warning: (protection.warning as string) ?? '',
			confirmation: (protection.confirmation as string) ?? ''
		})),
		replayWindow: (payload.replayWindow as Plan['replayWindow']) ?? { mode: 'full' },
		plannedAt: (payload.plannedAt as string) ?? '',
		command: (payload.command as string) ?? 'stb build'
	};
}

function sqlChangeFromServer(
	item: Payload | null
): Plan['entries'][number]['sqlChange'] {
	if (item === null) return null;
	return {
		status: item.status as PlanSqlChangeStatus,
		unifiedDiff: (item.unifiedDiff as string | null) ?? null,
		warning: (item.warning as string | null) ?? null
	};
}

function operationFromServer(item: Payload): Plan['teardown'][number] {
	return {
		relationName: item.relationName as string,
		action: item.action === 'create' ? 'create' : 'drop',
		modelName: (item.modelName as string) ?? '',
		resourceKind: item.resourceKind as Plan['teardown'][number]['resourceKind']
	};
}

function parseUserScope(token: string): Plan['userScope'][number] {
	return token.startsWith('pipeline:')
		? { kind: 'pipeline', name: token.slice('pipeline:'.length) }
		: { kind: 'model', name: token };
}

function signatureFromSource(source: string, name: string): string {
	const match = source.match(new RegExp(`def\\s+${name}\\s*\\(([^)]*)\\)`));
	return match ? `${name}(${match[1]})` : `${name}(…)`;
}

function retentionDaysFromTtl(ttl: string | null): number | null {
	if (ttl === null) return null;
	const match = ttl.match(/INTERVAL\s+(\d+)\s+DAY/i);
	return match ? Number(match[1]) : null;
}

/**
 * Fold recorded outcomes from `_streambuild_node_results` into the project.
 * CLI runs and UI runs share that history, so a refresh no longer forgets what
 * passed. Never overwrites a FRESHER in-session run.
 */
export function applyRecordedCheckStatuses(
	project: Project,
	statuses: CheckStatusRecord[]
): void {
	for (const record of statuses) {
		if (record.status === 'never_run' || record.completedAt === null) continue;
		if (record.kind === 'audit') applyAuditStatus(project, record);
		else applyTestStatus(project, record);
	}
}

function recordedIso(completedAt: string): string {
	return `${completedAt.replace(' ', 'T')}Z`;
}

function recordedPassed(record: CheckStatusRecord): boolean {
	if (record.status === 'passed') return true;
	return record.driftReasons.length > 0 && record.failureCount === 0 && record.errorMessage === null;
}

function isNewerThanExisting(checkedAt: string | undefined, record: CheckStatusRecord): boolean {
	if (checkedAt === undefined) return true;
	return Date.parse(recordedIso(record.completedAt ?? '')) >= Date.parse(checkedAt);
}

function applyAuditStatus(project: Project, record: CheckStatusRecord): void {
	const audit = project.audits.find((item) => item.name === record.name);
	if (!audit || !isNewerThanExisting(audit.result?.checkedAt, record)) return;
	const payload = record.payload ?? {};
	audit.result = {
		passed: recordedPassed(record),
		failingRowCount: record.failureCount,
		sampleColumns: (payload.sample_column_names as string[]) ?? [],
		sampleRows: (payload.sample_rows as CellValue[][]) ?? [],
		checkedAt: recordedIso(record.completedAt ?? ''),
		driftReasons: record.driftReasons,
		deferredUntil: (payload.eligible_at as string | null) ?? null
	};
}

function applyTestStatus(project: Project, record: CheckStatusRecord): void {
	const test = project.tests.find((item) => item.name === record.name);
	if (!test || !isNewerThanExisting(test.result?.checkedAt, record)) return;
	const payload = record.payload ?? {};
	const targets = ((payload.targets as Payload[]) ?? []).map((target) => ({
		targetModelName: String(target.target_model_name ?? target.name ?? ''),
		passed: Boolean(
			target.passed ??
				(((target.missing_rows as unknown[]) ?? []).length === 0 &&
					((target.unexpected_rows as unknown[]) ?? []).length === 0)
		),
		columns: (target.columns as string[]) ?? [],
		missingRows: (target.missing_rows as CellValue[][]) ?? [],
		unexpectedRows: (target.unexpected_rows as CellValue[][]) ?? []
	}));
	test.result = {
		passed: recordedPassed(record),
		targets,
		checkedAt: recordedIso(record.completedAt ?? ''),
		errorMessage: record.errorMessage,
		driftReasons: record.driftReasons
	};
}
