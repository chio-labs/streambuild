import { buildLogicalGraph } from '$lib/domain/main/graphs/build-logical-graph';
import { buildPhysicalGraph } from '$lib/domain/main/graphs/build-physical-graph';
import { modelByName } from '$lib/domain/main/lookups/model-by-name';
import type { Deployment, Project } from '$lib/domain/types';
import type {
	LineageCounts,
	LineageFilterState,
	LineageViewSnapshot,
	NodeKindFilter
} from '$lib/lineage-view/types';
import type { Graph, GraphNode } from '$lib/lineage/types';
import { readLineageFilters, readLineageMode } from '$lib/lineage-view/_helpers/lineage-location';

function filterCount(filters: LineageFilterState): number {
	return (
		(filters.search.trim() ? 1 : 0) +
		filters.pipelines.size +
		filters.kinds.size +
		filters.statuses.size +
		(filters.anchorsOnly ? 1 : 0)
	);
}

function nodeKind(project: Project, node: GraphNode): NodeKindFilter {
	if (node.logicalType === 'source') return 'source';
	if (node.logicalType === 'view') return 'view';
	return modelByName(project, node.logicalName)?.isAggregate ? 'aggregate' : 'table';
}

function matchesNode(project: Project, filters: LineageFilterState, node: GraphNode): boolean {
	const needle: string = filters.search.trim().toLowerCase();
	if (needle && !`${node.label} ${node.logicalName} ${node.sublabel ?? ''}`.toLowerCase().includes(needle)) {
		return false;
	}
	if (filters.pipelines.size) {
		const pipeline: string | undefined = modelByName(project, node.logicalName)?.pipeline;
		const feedsSelected: boolean =
			node.logicalType === 'source' &&
			project.pipelines.some(
				(candidate) => filters.pipelines.has(candidate.name) && candidate.sourceName === node.logicalName
			);
		if (!feedsSelected && (!pipeline || !filters.pipelines.has(pipeline))) return false;
	}
	if (filters.kinds.size && !filters.kinds.has(nodeKind(project, node))) return false;
	if (filters.statuses.size && !filters.statuses.has(node.status)) return false;
	if (filters.anchorsOnly && node.anchor !== 'eligible') return false;
	return true;
}

function narrowGraph(project: Project, filters: LineageFilterState, fullGraph: Graph): Graph {
	if (filterCount(filters) === 0) return fullGraph;
	const kept: Set<string> = new Set(
		fullGraph.nodes.filter((node) => matchesNode(project, filters, node)).map((node) => node.id)
	);
	return {
		nodes: fullGraph.nodes.filter((node) => kept.has(node.id)),
		edges: fullGraph.edges.filter((edge) => kept.has(edge.source) && kept.has(edge.target))
	};
}

function countStatuses(graph: Graph): LineageCounts {
	let fresh: number = 0;
	let lagging: number = 0;
	let stalled: number = 0;
	let drift: number = 0;
	let unknown: number = 0;
	for (const node of graph.nodes) {
		if (node.status === 'fresh') fresh += 1;
		if (node.status === 'lagging') lagging += 1;
		if (node.status === 'stalled') stalled += 1;
		if (node.status === 'drift') drift += 1;
		if (node.status === 'unknown') unknown += 1;
	}
	return { fresh, lagging, stalled, drift, unknown };
}

export function buildLineageSnapshot(
	url: URL,
	project: Project,
	deployments: Deployment[]
): LineageViewSnapshot {
	const mode: LineageViewSnapshot['mode'] = readLineageMode(url);
	const filters: LineageFilterState = readLineageFilters(url);
	const showDeployments: boolean = url.searchParams.get('deployments') === '1';
	const fullGraph: Graph =
		mode === 'logical'
			? buildLogicalGraph(project)
			: buildPhysicalGraph(project, showDeployments ? deployments : []);
	const graph: Graph = narrowGraph(project, filters, fullGraph);
	return { mode, filters, showDeployments, fullGraph, graph, counts: countStatuses(graph) };
}
