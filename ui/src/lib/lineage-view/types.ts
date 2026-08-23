import type { Deployment, ModelStatus, Project } from '$lib/domain/types';
import type { Graph, GraphMode, GraphNode } from '$lib/lineage/types';

export type NodeKindFilter = 'source' | 'table' | 'aggregate' | 'view';

export type LineageFilterState = {
	search: string;
	pipelines: Set<string>;
	kinds: Set<NodeKindFilter>;
	statuses: Set<ModelStatus>;
	anchorsOnly: boolean;
};

export type LineageCounts = {
	readonly fresh: number;
	readonly lagging: number;
	readonly stalled: number;
	readonly drift: number;
	readonly unknown: number;
};

export type LineageViewSnapshot = {
	readonly mode: GraphMode;
	readonly filters: LineageFilterState;
	readonly showDeployments: boolean;
	readonly fullGraph: Graph;
	readonly graph: Graph;
	readonly counts: LineageCounts;
};

export type LineageViewTypes = {
	project: Project;
	mode: GraphMode;
	node: GraphNode;
	filters: LineageFilterState;
};

export type LineageViewFacade = {
	snapshot(url: URL, project: Project, deployments: Deployment[]): LineageViewSnapshot;
	filtersUrl(url: URL, filters: LineageFilterState): URL;
	deploymentsUrl(url: URL, showDeployments: boolean): URL;
	groupUrl(url: URL, groupMode: 'none' | 'boxes' | 'lanes'): URL;
	modeUrl(url: URL, mode: GraphMode): URL;
};
