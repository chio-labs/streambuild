/**
 * Maps dev-server payloads onto the UI domain model.
 *
 * The server payloads were designed against these types, so most of this is
 * mechanical renaming plus the handful of derivations that are cheaper client
 * side (partition lag, replay roles from column names, macro signatures).
 */

import type {
	AnchorState,
	Audit,
	Column,
	Model,
	ModelStatus,
	PartitionState,
	Pipeline,
	Plan,
	Project,
	ReplayRole,
	Source,
	SqlTest
} from '$lib/domain/types';

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
	const models = (definitions.models as Payload[]).map((model) =>
		modelFromServer(model, stateFor(state, 'models', model.name as string))
	);
	return {
		name: (header.name as string) ?? 'project',
		target: (header.target as string) ?? '',
		database: (header.database as string) ?? '',
		adapter: (header.adapter as string) ?? 'clickhouse',
		virtualEnvironments: false,
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
		defaults: { managedSourceTtl: (defaults.managedSourceTtl as string | null) ?? null },
		toolVersion: 'dev',
		warehouseTimezone: 'UTC',
		capturedAt: (state.capturedAt as string) ?? new Date().toISOString(),
		sources: (definitions.sources as Payload[]).map((source) =>
			sourceFromServer(source, stateFor(state, 'sources', source.name as string), state)
		),
		pipelines: (definitions.pipelines as Payload[]).map(pipelineFromServer),
		models,
		audits: (definitions.audits as Payload[]).map(auditFromServer),
		tests: (definitions.tests as Payload[]).map(testFromServer),
		macros: (definitions.macros as Payload[]).map((macro) => ({
			name: macro.name as string,
			file: macro.file as string,
			signature: signatureFromSource(macro.source as string, macro.name as string),
			description: null
		}))
	};
}

function stateFor(state: Payload, section: string, name: string): Payload {
	const bucket = (state[section] ?? {}) as Record<string, Payload>;
	return bucket[name] ?? {};
}

function sourceFromServer(source: Payload, live: Payload, state: Payload): Source {
	const kafka = (source.kafka ?? null) as Payload | null;
	const throughput = (live.throughput ?? null) as Payload | null;
	const buckets = (throughput?.buckets ?? []) as number[];
	const capturedAt = (state.capturedAt as string) ?? '';
	return {
		name: source.name as string,
		kind: source.kind === 'kafka' ? 'kafka' : 'stream_table',
		boundaryMode: source.boundaryMode as Source['boundaryMode'],
		relationName: source.relationName as string,
		managedRelations: ((source.managedRelations ?? []) as Payload[]).map((relation) => ({
			kind: relation.kind as Source['managedRelations'][number]['kind'],
			name: relation.name as string,
			engine: '',
			note: ''
		})),
		ttl: (source.ttl as string | null) ?? null,
		retentionDays: retentionDaysFromTtl((source.ttl as string | null) ?? null),
		ttlFromProjectDefault: false,
		brokerList: (kafka?.brokerList as string) ?? null,
		topic: (kafka?.topic as string) ?? null,
		consumerGroup: (kafka?.consumerGroup as string) ?? null,
		format: (kafka?.format as string) ?? null,
		settings: (kafka?.settings as Record<string, string> | null) ?? null,
		columnMapping: (source.columnMapping as Source['columnMapping']) ?? null,
		live: {
			rowsPerSecond: (live.rowsPerSecond as number) ?? 0,
			lagSeconds: (live.lagSeconds as number | null) ?? null,
			newestEventAt: (live.newestEventAt as string) ?? '',
			oldestEventAt: (live.oldestEventAt as string) ?? '',
			rows: (live.rows as number) ?? 0,
			partitions: ((live.partitions ?? []) as Payload[]).map((partition) =>
				partitionFromServer(partition, capturedAt)
			),
			throughput: buckets
		}
	};
}

function partitionFromServer(partition: Payload, capturedAt: string): PartitionState {
	const newest = (partition.newestEventAt as string) ?? '';
	return {
		partition: partition.partition as number,
		offset: (partition.maxOffset as number) ?? 0,
		lagSeconds: ageSeconds(newest, capturedAt) ?? 0,
		newestEventAt: newest
	};
}

function pipelineFromServer(pipeline: Payload): Pipeline {
	const file = (pipeline.file as string) ?? '';
	const naming = (pipeline.naming ?? {}) as Payload;
	return {
		name: pipeline.name as string,
		sourceName: (pipeline.sourceName as string | null) ?? null,
		boundaryMode: (pipeline.boundaryMode as Pipeline['boundaryMode']) ?? null,
		models: (pipeline.models as string[]) ?? [],
		naming: {
			tablePrefix: (naming.tablePrefix as string | null) ?? null,
			viewPrefix: (naming.viewPrefix as string | null) ?? null
		},
		directory: file.replace(/\/[^/]*$/, '')
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
			ownership: ((live.ownership as string) ?? 'absent') as Model['live']['ownership'],
			recordedCoverage: null
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
	const file = (audit.file as string) ?? '';
	const generic = !file.includes('audits/');
	return {
		name: audit.name as string,
		file,
		severity: (audit.severity as Audit['severity']) ?? 'error',
		description: (audit.description as string | null) ?? null,
		referencedModels: (audit.referencedModels as string[]) ?? [],
		generic,
		genericName: null,
		sql: (audit.sql as string) ?? '',
		result: null
	};
}

function testFromServer(test: Payload): SqlTest {
	return {
		name: test.name as string,
		file: (test.file as string) ?? '',
		targets: (test.targets as string[]) ?? [],
		sql: (test.sql as string) ?? '',
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
			isReplayRoot: Boolean(entry.isReplayRoot)
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
			replayColumns: {},
			propagatedModelNames: (root.propagatedModelNames as string[]) ?? [],
			hasAggregateSemantics: Boolean(root.hasAggregateSemantics)
		})),
		warnings: ((payload.warnings as Payload[]) ?? []).map((warning) => ({
			code: (warning.code as string) ?? '',
			message: (warning.message as string) ?? '',
			relatedModel: null
		})),
		replayWindow: (payload.replayWindow as Plan['replayWindow']) ?? { mode: 'full' },
		estimate: null,
		plannedAt: (payload.plannedAt as string) ?? '',
		command: (payload.command as string) ?? 'stb build'
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

function ageSeconds(newest: string, capturedAt: string): number | null {
	if (!newest || !capturedAt) return null;
	const newestMs = Date.parse(newest.replace(' ', 'T') + 'Z');
	const nowMs = Date.parse(capturedAt.replace(' ', 'T') + 'Z');
	if (Number.isNaN(newestMs) || Number.isNaN(nowMs)) return null;
	return Math.round((nowMs - newestMs) / 100) / 10;
}
