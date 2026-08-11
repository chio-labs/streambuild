import type { ReplayRole } from '$lib/domain/types';

type ReplayBoundaryMode = 'offsets' | 'timestamp' | 'landed_at' | 'cursor';
type OwnershipState = 'direct' | 'unmanaged' | 'conflicted' | 'absent' | 'virtual_environment';
type PlanEntryReason = 'selected' | 'downstream_of_selected' | 'all_models';
type PlanSqlChange = {
	status: PlanSqlChangeStatus;
	unifiedDiff: string | null;
	warning: string | null;
};
type PlanEntry = {
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
type PlanAction = {
	relationName: string;
	action: 'drop' | 'create';
	modelName: string;
	resourceKind: 'table' | 'materialized_view' | 'view';
};
type PlanReplayRoot = {
	modelName: string;
	drivingInputName: string;
	drivingInputRelationName: string;
	boundaryMode: ReplayBoundaryMode;
	replayColumns: Partial<Record<ReplayRole, string>>;
	propagatedModelNames: string[];
	hasAggregateSemantics: boolean;
	rowsToReplay: number | null;
};
type PlanWarning = { code: string; message: string; relatedModel: string | null };
type PlanProtection = { pipelineName: string; warning: string; confirmation: string };
type PlanPrerequisite = {
	name: string;
	type: 'source' | 'model';
	relationNames: string[];
	present: boolean;
	frameworkManaged: boolean;
};

export type Selector = { kind: 'model' | 'pipeline'; name: string };
export type PlanSqlChangeStatus =
	| 'first_baseline'
	| 'query_changed'
	| 'no_query_change'
	| 'baseline_unavailable';
export type ReplayWindow = { mode: 'full' } | { mode: 'from'; startTime: string };
export type Plan = {
	adapter: string;
	database: string;
	userScope: Selector[];
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
