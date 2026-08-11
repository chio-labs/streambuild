import type { AnchorState, ModelStatus, RefType } from '$lib/domain/types';

type LogicalNodeType = 'source' | 'model' | 'view';
type PhysicalNodeType =
	| 'kafka_engine'
	| 'landing_mv'
	| 'landing_table'
	| 'adopted_table'
	| 'model_mv'
	| 'model_table'
	| 'model_view';
type RelationDeploymentState = 'active' | 'staged' | 'orphaned';
type NodeDeployment = { deploymentId: string; state: RelationDeploymentState };

export type GraphMode = 'logical' | 'physical';

export type GraphNode = {
	id: string;
	label: string;
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
	deployment?: NodeDeployment | null;
};

export type GraphEdge = {
	id: string;
	source: string;
	target: string;
	type: RefType;
	flowState: 'flowing' | 'stalled' | 'unknown';
};

export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

export type NodeFieldSet = {
	kind: boolean;
	status: boolean;
	relation: boolean;
	anchor: boolean;
	checks: boolean;
	rows: boolean;
	rate: boolean;
};

export type NodeFieldController = {
	readonly value: NodeFieldSet;
	toggle(field: keyof NodeFieldSet): void;
	reset(): void;
};
