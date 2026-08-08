/**
 * Everything the UI needs that isn't hand-authored in `mock.ts`.
 *
 * Keeping derivation here is what stops the six-divergent-mocks problem: the
 * physical graph, the stream tree, the rebuild closure, the plan and the
 * reconstruction analysis are all computed from one fixture.
 */

import {
	type Audit,
	type Graph,
	type GraphEdge,
	type GraphNode,
	type Model,
	type Plan,
	type PlanAction,
	type PlanEntry,
	type PlanEntryReason,
	type PlanPrerequisite,
	type PlanReplayRoot,
	type PlanWarning,
	type Pipeline,
	type Project,
	type ReconstructionCoverage,
	type ReconstructionState,
	type ReplayWindow,
	type Selector,
	type Source,
	type SqlTest
} from '$lib/domain/types';
import { daysBetween, formatEngineFamily, secondsBetween } from '$lib/domain/format';

// ─── lookups ─────────────────────────────────────────────────────────────────

export function modelByName(project: Project, name: string): Model | undefined {
	return project.models.find((model) => model.name === name);
}

export function sourceByName(project: Project, name: string): Source | undefined {
	return project.sources.find((source) => source.name === name);
}

export function pipelineByName(project: Project, name: string): Pipeline | undefined {
	return project.pipelines.find((pipeline) => pipeline.name === name);
}

export function modelsInPipeline(project: Project, pipelineName: string): Model[] {
	return project.models.filter((model) => model.pipeline === pipelineName);
}

// ─── checks ──────────────────────────────────────────────────────────────────

export function auditsForModel(project: Project, modelName: string): Audit[] {
	return project.audits.filter((audit) => audit.referencedModels.includes(modelName));
}

export function testsForModel(project: Project, modelName: string): SqlTest[] {
	return project.tests.filter((test) => test.targets.includes(modelName));
}

export type CheckCounts = { total: number; passing: number; warning: number; failing: number };

export function auditCounts(audits: Audit[]): CheckCounts {
	let passing = 0;
	let warning = 0;
	let failing = 0;
	for (const audit of audits) {
		if (!audit.result) continue;
		if (audit.result.deferredUntil) continue;
		if (audit.result.passed) passing += 1;
		else if (audit.severity === 'warning') warning += 1;
		else failing += 1;
	}
	return { total: audits.length, passing, warning, failing };
}

export function testCounts(tests: SqlTest[]): CheckCounts {
	let passing = 0;
	let failing = 0;
	for (const test of tests) {
		if (!test.result) continue;
		if (test.result.passed) passing += 1;
		else failing += 1;
	}
	return { total: tests.length, passing, warning: 0, failing };
}

// ─── graph: logical ──────────────────────────────────────────────────────────



/**
 * Whether rows are still moving through this model — what the animated driving
 * edge encodes.
 *
 * Deliberately NOT derived from lag. Lag measures how far BEHIND the output is;
 * it says nothing about whether it is moving. A model ten minutes behind but
 * catching up at full throughput is flowing, arguably harder than one sitting
 * at two seconds. Treating lag as a proxy for motion made every slow-cadence
 * input — a cursor-polled dimension feed, say — look stopped when it was
 * merely behind.
 *
 * `stalled` is the status that actually means stopped, and is what the graph
 * header already counts.
 */
function isFlowing(model: Model): boolean {
	return model.kind === 'table' && model.live.lagSeconds !== null && model.status !== 'stalled';
}

function sourceGraphNode(project: Project, source: Source): GraphNode {
	return {
		id: `source:${source.name}`,
		label: source.name,
		logicalName: source.name,
		logicalType: 'source',
		physicalType: null,
		status: 'source',
		anchor: null,
		kindLabel: source.kind === 'kafka' ? 'KAFKA SOURCE' : 'ADOPTED SOURCE',
		sublabel: source.kind === 'kafka' ? source.topic : source.relationName,
		rows: source.live.rows,
		rowsPerSecond: source.live.rowsPerSecond,
		failingChecks: 0,
		warningChecks: 0,
		totalChecks: 0,
		drift: false
	};
}

function modelGraphNode(project: Project, model: Model): GraphNode {
	const counts: CheckCounts = auditCounts(auditsForModel(project, model.name));
	return {
		id: `model:${model.name}`,
		label: model.name,
		logicalName: model.name,
		logicalType: model.kind === 'view' ? 'view' : 'model',
		physicalType: null,
		status: model.status,
		anchor: model.anchor,
		kindLabel: model.kind === 'view' ? 'TERMINAL VIEW' : formatEngineFamily(model.storage.engine),
		sublabel: model.relationName,
		rows: model.live.rows,
		rowsPerSecond: null,
		failingChecks: counts.failing,
		warningChecks: counts.warning,
		totalChecks: counts.total,
		drift: !model.live.inSyncWithCompiled
	};
}

export function buildLogicalGraph(project: Project): Graph {
	const nodes: GraphNode[] = [
		...project.sources.map((source) => sourceGraphNode(project, source)),
		...project.models.map((model) => modelGraphNode(project, model))
	];

	const edges: GraphEdge[] = [];
	for (const model of project.models) {
		for (const ref of model.refs) {
			const fromId = ref.isSource ? `source:${ref.name}` : `model:${ref.name}`;
			edges.push({
				id: `${fromId}->model:${model.name}:${ref.type}`,
				source: fromId,
				target: `model:${model.name}`,
				type: ref.type,
				flowing: ref.type === 'driving_input' && isFlowing(model)
			});
		}
	}

	return { nodes, edges };
}

// ─── graph: physical ─────────────────────────────────────────────────────────

/**
 * Expands every logical node into the real ClickHouse objects. This is the view
 * operators actually debug and it exists in no other tool:
 *
 *   kafka__x ─▶ mv__x ─▶ raw__x ─▶ mv__model ─▶ tbl__model
 */
export function buildPhysicalGraph(project: Project): Graph {
	const nodes: GraphNode[] = [];
	const edges: GraphEdge[] = [];

	/** Logical name → the relation downstream MVs should read from. */
	const readRelationId = new Map<string, string>();

	for (const source of project.sources) {
		// Resolved by KIND, never by array position: the server serializes managed
		// relations in realization order (kafka engine, landing table, landing MV),
		// which is not the mock-era ordering this code once assumed.
		const kafkaRelation = source.managedRelations.find((r) => r.kind === 'kafka_engine');
		const mvRelation = source.managedRelations.find((r) => r.kind === 'landing_mv');
		const rawRelation = source.managedRelations.find((r) => r.kind === 'landing_table');
		if (source.kind === 'kafka' && kafkaRelation && mvRelation && rawRelation) {
			const kafkaId = `rel:${kafkaRelation.name}`;
			const mvId = `rel:${mvRelation.name}`;
			const rawId = `rel:${rawRelation.name}`;

			nodes.push({
				id: kafkaId,
				label: kafkaRelation.name,
				logicalName: source.name,
				logicalType: 'source',
				physicalType: 'kafka_engine',
				status: 'source',
				anchor: null,
				kindLabel: 'KAFKA ENGINE',
				sublabel: source.topic,
				rows: null,
				rowsPerSecond: source.live.rowsPerSecond,
				failingChecks: 0,
				warningChecks: 0,
				totalChecks: 0,
				drift: false
			});
			nodes.push({
				id: mvId,
				label: mvRelation.name,
				logicalName: source.name,
				logicalType: 'source',
				physicalType: 'landing_mv',
				status: 'source',
				anchor: null,
				kindLabel: 'LANDING MV',
				sublabel: null,
				rows: null,
				rowsPerSecond: source.live.rowsPerSecond,
				failingChecks: 0,
				warningChecks: 0,
				totalChecks: 0,
				drift: false
			});
			nodes.push({
				id: rawId,
				label: rawRelation.name,
				logicalName: source.name,
				logicalType: 'source',
				physicalType: 'landing_table',
				status: 'source',
				anchor: null,
				kindLabel: 'LANDING TABLE',
				sublabel: source.ttl ? `TTL ${source.retentionDays}d` : 'no TTL',
				rows: source.live.rows,
				rowsPerSecond: source.live.rowsPerSecond,
				failingChecks: 0,
				warningChecks: 0,
				totalChecks: 0,
				drift: false
			});

			edges.push({
				id: `${kafkaId}->${mvId}`,
				source: kafkaId,
				target: mvId,
				type: 'driving_input',
				flowing: true
			});
			edges.push({
				id: `${mvId}->${rawId}`,
				source: mvId,
				target: rawId,
				type: 'driving_input',
				flowing: true
			});
			readRelationId.set(source.name, rawId);
		} else {
			const adoptedId = `rel:${source.relationName}`;
			nodes.push({
				id: adoptedId,
				label: source.relationName,
				logicalName: source.name,
				logicalType: 'source',
				physicalType: 'adopted_table',
				status: 'source',
				anchor: null,
				kindLabel: 'ADOPTED TABLE',
				sublabel: 'not owned by StreamBuild',
				rows: source.live.rows,
				rowsPerSecond: source.live.rowsPerSecond,
				failingChecks: 0,
				warningChecks: 0,
				totalChecks: 0,
				drift: false
			});
			readRelationId.set(source.name, adoptedId);
		}
	}

	for (const model of project.models) {
		const counts: CheckCounts = auditCounts(auditsForModel(project, model.name));
		const tableId = `rel:${model.relationName}`;

		if (model.kind === 'view') {
			nodes.push({
				id: tableId,
				label: model.relationName,
				logicalName: model.name,
				logicalType: 'view',
				physicalType: 'model_view',
				status: model.status,
				anchor: model.anchor,
				kindLabel: 'VIEW',
				sublabel: null,
				rows: null,
				rowsPerSecond: null,
				failingChecks: counts.failing,
				warningChecks: counts.warning,
				totalChecks: counts.total,
				drift: !model.live.inSyncWithCompiled
			});
			readRelationId.set(model.name, tableId);
			continue;
		}

		const mvId = `rel:${model.mvRelationName}`;
		nodes.push({
			id: mvId,
			label: model.mvRelationName ?? '',
			logicalName: model.name,
			logicalType: 'model',
			physicalType: 'model_mv',
			status: model.status,
			anchor: null,
			kindLabel: 'MODEL MV',
			sublabel: null,
			rows: null,
			rowsPerSecond: null,
			failingChecks: 0,
			warningChecks: 0,
			totalChecks: 0,
			drift: false
		});
		nodes.push({
			id: tableId,
			label: model.relationName,
			logicalName: model.name,
			logicalType: 'model',
			physicalType: 'model_table',
			status: model.status,
			anchor: model.anchor,
			kindLabel: formatEngineFamily(model.storage.engine),
			sublabel: null,
			rows: model.live.rows,
			rowsPerSecond: null,
			failingChecks: counts.failing,
			warningChecks: counts.warning,
			totalChecks: counts.total,
			drift: !model.live.inSyncWithCompiled
		});
		edges.push({
			id: `${mvId}->${tableId}`,
			source: mvId,
			target: tableId,
			type: 'driving_input',
			flowing: isFlowing(model)
		});
		readRelationId.set(model.name, tableId);
	}

	// Wire each model's inputs into the MV that writes it (or into the view itself).
	for (const model of project.models) {
		const targetId = model.kind === 'view' ? `rel:${model.relationName}` : `rel:${model.mvRelationName}`;
		for (const ref of model.refs) {
			const fromId = readRelationId.get(ref.name);
			if (!fromId) continue;
			edges.push({
				id: `${fromId}->${targetId}:${ref.type}`,
				source: fromId,
				target: targetId,
				type: ref.type,
				flowing: ref.type === 'driving_input' && isFlowing(model)
			});
		}
	}

	return { nodes, edges };
}

// ─── stream tree ─────────────────────────────────────────────────────────────

export type StreamTreeRow = {
	kind: 'source' | 'model';
	name: string;
	depth: number;
	/** Vertical guide state for each ancestor level, for drawing tree connectors. */
	ancestorHasNext: boolean[];
	isLast: boolean;
	model: Model | null;
	source: Source | null;
};

/**
 * The driving-input graph inside a pipeline is a TREE, because every table model
 * has exactly one driving input. That is why a pipeline reads well as an
 * indented list and a dbt DAG never can.
 */
export function streamTree(project: Project, pipelineName: string): StreamTreeRow[] {
	const pipeline: Pipeline | undefined = pipelineByName(project, pipelineName);
	if (!pipeline) return [];

	const models: Model[] = modelsInPipeline(project, pipelineName);
	const childrenOf = new Map<string, Model[]>();
	const roots: Model[] = [];

	for (const model of models) {
		const parent: string | null = model.drivingInput;
		const parentIsModelInPipeline: boolean =
			parent !== null && models.some((candidate) => candidate.name === parent);
		if (parentIsModelInPipeline && parent) {
			const bucket: Model[] = childrenOf.get(parent) ?? [];
			bucket.push(model);
			childrenOf.set(parent, bucket);
		} else {
			roots.push(model);
		}
	}

	const rows: StreamTreeRow[] = [];

	const source: Source | undefined = pipeline.sourceName
		? sourceByName(project, pipeline.sourceName)
		: undefined;
	if (source) {
		rows.push({
			kind: 'source',
			name: source.name,
			depth: 0,
			ancestorHasNext: [],
			isLast: false,
			model: null,
			source
		});
	}

	const baseDepth: number = source ? 1 : 0;

	function walk(model: Model, depth: number, ancestorHasNext: boolean[], isLast: boolean): void {
		rows.push({
			kind: 'model',
			name: model.name,
			depth,
			ancestorHasNext,
			isLast,
			model,
			source: null
		});
		const children: Model[] = childrenOf.get(model.name) ?? [];
		children.forEach((child, index) => {
			walk(child, depth + 1, [...ancestorHasNext, !isLast], index === children.length - 1);
		});
	}

	roots.forEach((root, index) => {
		walk(root, baseDepth, [], index === roots.length - 1);
	});

	return rows;
}

// ─── selection & closure ─────────────────────────────────────────────────────

export function parseSelector(token: string): Selector | null {
	const trimmed: string = token.trim();
	if (!trimmed) return null;
	if (trimmed.startsWith('pipeline:')) {
		const name: string = trimmed.slice('pipeline:'.length);
		return name ? { kind: 'pipeline', name } : null;
	}
	return { kind: 'model', name: trimmed };
}

export function selectorToken(selector: Selector): string {
	return selector.kind === 'pipeline' ? `pipeline:${selector.name}` : selector.name;
}

/** Downstream neighbours across every edge type. */
function downstreamMap(project: Project): Map<string, string[]> {
	const map = new Map<string, string[]>();
	for (const model of project.models) {
		for (const ref of model.refs) {
			if (ref.isSource) continue;
			const bucket: string[] = map.get(ref.name) ?? [];
			bucket.push(model.name);
			map.set(ref.name, bucket);
		}
	}
	return map;
}

export type Closure = {
	/** Exactly what the selectors named. */
	selected: Set<string>;
	/** Selected plus every downstream model. Direct plans are never pruned. */
	all: Set<string>;
	reasonByModel: Map<string, PlanEntryReason>;
};

export function resolveClosure(project: Project, selectors: Selector[]): Closure {
	const selected = new Set<string>();

	if (selectors.length === 0) {
		const all = new Set<string>(project.models.map((model) => model.name));
		const reasonByModel = new Map<string, PlanEntryReason>();
		for (const name of all) reasonByModel.set(name, 'all_models');
		return { selected: all, all, reasonByModel };
	}

	for (const selector of selectors) {
		if (selector.kind === 'pipeline') {
			for (const model of modelsInPipeline(project, selector.name)) selected.add(model.name);
		} else if (modelByName(project, selector.name)) {
			selected.add(selector.name);
		}
	}

	const downstream: Map<string, string[]> = downstreamMap(project);
	const all = new Set<string>(selected);
	const stack: string[] = [...selected];
	while (stack.length) {
		const current: string = stack.pop() as string;
		for (const child of downstream.get(current) ?? []) {
			if (!all.has(child)) {
				all.add(child);
				stack.push(child);
			}
		}
	}

	const reasonByModel = new Map<string, PlanEntryReason>();
	for (const name of all) {
		reasonByModel.set(name, selected.has(name) ? 'selected' : 'downstream_of_selected');
	}

	return { selected, all, reasonByModel };
}

/** Dependency order (inputs first). Used for creation; reversed for teardown. */
export function topologicalModelOrder(project: Project, names: Set<string>): string[] {
	const ordered: string[] = [];
	const visited = new Set<string>();

	function visit(name: string): void {
		if (visited.has(name)) return;
		visited.add(name);
		const model: Model | undefined = modelByName(project, name);
		if (model) {
			for (const ref of model.refs) {
				if (!ref.isSource && names.has(ref.name)) visit(ref.name);
			}
		}
		ordered.push(name);
	}

	for (const name of names) visit(name);
	return ordered;
}

// ─── reconstruction ──────────────────────────────────────────────────────────

/**
 * Model tables are disposable derivations of `raw__*`; the source TTL is the
 * durability setting. So a model holding MORE history than its source retains
 * is a standing latent truncation — the next rebuild silently drops the
 * overhang. The CLI never tells you this.
 */
export function reconstructionCoverage(project: Project): ReconstructionCoverage[] {
	const rows: ReconstructionCoverage[] = [];

	for (const model of project.models) {
		if (model.kind === 'view') continue;
		const source: Source | undefined = rootSourceFor(project, model);
		if (!source || !model.live.oldestRowAt) {
			rows.push({
				modelName: model.name,
				sourceName: source?.name ?? '—',
				state: 'unknown',
				heldFrom: model.live.oldestRowAt,
				retainedFrom: source?.live.oldestEventAt ?? null,
				heldDays: null,
				retainedDays: null,
				unreconstructableDays: null
			});
			continue;
		}

		const reference: string = project.capturedAt;
		const heldDays: number = daysBetween(model.live.oldestRowAt, reference);
		const retainedDays: number = daysBetween(source.live.oldestEventAt, reference);

		let state: ReconstructionState;
		if (source.retentionDays === null) state = 'lossless';
		else if (heldDays - retainedDays > 1) state = 'truncating';
		else state = 'matched';

		rows.push({
			modelName: model.name,
			sourceName: source.name,
			state,
			heldFrom: model.live.oldestRowAt,
			retainedFrom: source.live.oldestEventAt,
			heldDays,
			retainedDays,
			unreconstructableDays: state === 'truncating' ? heldDays - retainedDays : 0
		});
	}

	return rows;
}

/** Walks driving inputs up to the source that roots this model's pipeline. */
export function rootSourceFor(project: Project, model: Model): Source | undefined {
	let current: Model | undefined = model;
	const seen = new Set<string>();
	while (current && current.drivingInput && !seen.has(current.name)) {
		seen.add(current.name);
		const source: Source | undefined = sourceByName(project, current.drivingInput);
		if (source) return source;
		current = modelByName(project, current.drivingInput);
	}
	return undefined;
}

// ─── rollups ─────────────────────────────────────────────────────────────────

export type FreshnessSummary = {
	fresh: number;
	lagging: number;
	stalled: number;
	drift: number;
	total: number;
	offenders: Model[];
};

export function freshnessSummary(project: Project): FreshnessSummary {
	let fresh = 0;
	let lagging = 0;
	let stalled = 0;
	let drift = 0;
	const offenders: Model[] = [];

	for (const model of project.models) {
		if (model.status === 'fresh') fresh += 1;
		if (model.status === 'lagging') {
			lagging += 1;
			offenders.push(model);
		}
		if (model.status === 'stalled') {
			stalled += 1;
			offenders.push(model);
		}
		if (model.status === 'drift') {
			drift += 1;
			offenders.push(model);
		}
	}

	return { fresh, lagging, stalled, drift, total: project.models.length, offenders };
}

export function driftedModels(project: Project): Model[] {
	return project.models.filter((model) => !model.live.inSyncWithCompiled);
}

export function truncatingCoverage(project: Project): ReconstructionCoverage[] {
	return reconstructionCoverage(project).filter((row) => row.state === 'truncating');
}

export function pipelineFreshness(project: Project, pipelineName: string): FreshnessSummary {
	const models: Model[] = modelsInPipeline(project, pipelineName);
	let fresh = 0;
	let lagging = 0;
	let stalled = 0;
	let drift = 0;
	const offenders: Model[] = [];
	for (const model of models) {
		if (model.status === 'fresh') fresh += 1;
		if (model.status === 'lagging') lagging += 1;
		if (model.status === 'stalled') stalled += 1;
		if (model.status === 'drift') drift += 1;
		if (model.status !== 'fresh') offenders.push(model);
	}
	return { fresh, lagging, stalled, drift, total: models.length, offenders };
}

export function anchorCount(project: Project, pipelineName: string): number {
	return modelsInPipeline(project, pipelineName).filter((model) => model.anchor === 'eligible')
		.length;
}

/**
 * Every stream source that ultimately feeds a set of models — walking driving
 * inputs up through intermediate models rather than only looking at direct
 * `__source` refs. This is what bounds the replay window on the Plan page.
 */
export function rootSourcesFor(project: Project, modelNames: Iterable<string>): Source[] {
	const found = new Map<string, Source>();
	for (const name of modelNames) {
		const model: Model | undefined = modelByName(project, name);
		if (!model) continue;
		const source: Source | undefined = rootSourceFor(project, model);
		if (source) found.set(source.name, source);
	}
	return [...found.values()];
}
