import type { Edge, Node } from '@xyflow/svelte';
import type { ModelStatus } from '$lib/domain/types';
import type { GraphEdge, GraphNode } from '$lib/lineage/types';
import { edgeClass } from '$lib/presentation/_helpers/lineage/flow-layout';

type StatusCounts = Record<ModelStatus, number>;

export type FlowPresentationOptions = {
	nodes: Node[];
	edges: Edge[];
	domainNodes: Map<string, GraphNode>;
	domainEdges: Map<string, GraphEdge>;
	groupKeyByNodeId: Map<string, string>;
	viewTargets: Set<string>;
	litEdgeIds: Set<string> | null;
};

export type FlowPresentationResult = {
	nodes: Node[];
	edges: Edge[];
};

export function graphTopologyKey(nodes: GraphNode[], edges: GraphEdge[]): string {
	return [
		nodes
			.map(
				(node) =>
					`${node.id}:${node.label}:${node.logicalName}:${node.logicalType}:` +
					`${node.physicalType}:${node.kindLabel}:${node.sublabel}:` +
					`${node.deployment?.deploymentId ?? ''}:${node.deployment?.state ?? ''}`
			)
			.join('|'),
		edges.map((edge) => `${edge.id}:${edge.source}>${edge.target}:${edge.type}`).join('|')
	].join('~');
}

export function refreshFlowNodes(options: FlowPresentationOptions): Node[] {
	const countsByGroup: Map<string, StatusCounts> = groupStatusCounts(
		options.domainNodes.values(),
		options.groupKeyByNodeId
	);
	let nodesChanged: boolean = false;
	const nodes: Node[] = options.nodes.map((node) => {
		const domainNode: GraphNode | undefined = options.domainNodes.get(node.id);
		if (domainNode && streamPresentationChanged(node, domainNode)) {
			nodesChanged = true;
			return { ...node, data: { ...node.data, ...domainNode } };
		}
		if (node.type !== 'collapsedGroup') return node;
		const groupKey: string = String(node.data.groupKey ?? '');
		const statusCounts: StatusCounts | undefined = countsByGroup.get(groupKey);
		if (!statusCounts || statusCountsEqual(node.data.statusCounts, statusCounts)) return node;
		nodesChanged = true;
		return { ...node, data: { ...node.data, statusCounts } };
	});

	return nodesChanged ? nodes : options.nodes;
}

export function refreshFlowEdges(options: FlowPresentationOptions): Edge[] {
	let edgesChanged: boolean = false;
	const edges: Edge[] = options.edges.map((edge) => {
		const domainEdge: GraphEdge | undefined = options.domainEdges.get(edge.id);
		if (!domainEdge) return edge;
		const dimmed: boolean = options.litEdgeIds !== null && !options.litEdgeIds.has(edge.id);
		const back: boolean = (edge.class ?? '').includes('sb-edge-back');
		const nextClass: string = edgeClass(
			domainEdge.type,
			domainEdge.flowState,
			dimmed,
			back,
			options.viewTargets.has(domainEdge.target)
		);
		const currentFlowState: unknown = edge.domAttributes?.['data-flow-state'];
		if (nextClass === edge.class && currentFlowState === domainEdge.flowState) return edge;
		edgesChanged = true;
		return {
			...edge,
			class: nextClass,
			domAttributes: { ...edge.domAttributes, 'data-flow-state': domainEdge.flowState }
		};
	});

	return edgesChanged ? edges : options.edges;
}

export function refreshFlowPresentation(options: FlowPresentationOptions): FlowPresentationResult {
	return {
		nodes: refreshFlowNodes(options),
		edges: refreshFlowEdges(options)
	};
}

function streamPresentationChanged(node: Node, domain: GraphNode): boolean {
	const data: Record<string, unknown> = node.data;
	return (
		data.status !== domain.status ||
		data.rows !== domain.rows ||
		data.rowsPerSecond !== domain.rowsPerSecond ||
		data.failingChecks !== domain.failingChecks ||
		data.warningChecks !== domain.warningChecks ||
		data.totalChecks !== domain.totalChecks ||
		data.drift !== domain.drift ||
		data.anchor !== domain.anchor
	);
}

function groupStatusCounts(
	nodes: Iterable<GraphNode>,
	groupKeyByNodeId: Map<string, string>
): Map<string, StatusCounts> {
	const countsByGroup: Map<string, StatusCounts> = new Map();
	for (const node of nodes) {
		const groupKey: string | undefined = groupKeyByNodeId.get(node.id);
		if (!groupKey) continue;
		const counts: StatusCounts =
			countsByGroup.get(groupKey) ??
			{ fresh: 0, lagging: 0, stalled: 0, drift: 0, unknown: 0, source: 0 };
		counts[node.status] += 1;
		countsByGroup.set(groupKey, counts);
	}
	return countsByGroup;
}

function statusCountsEqual(current: unknown, next: StatusCounts): boolean {
	if (!current || typeof current !== 'object') return false;
	const counts: Partial<StatusCounts> = current as Partial<StatusCounts>;
	return Object.entries(next).every(
		([status, count]) => counts[status as ModelStatus] === count
	);
}
