import type { Edge, Node } from '@xyflow/svelte';
import type { ModelStatus, Project, RefType } from '$lib/domain/types';
import type { Graph, GraphEdge, GraphNode, GroupMode } from '$lib/lineage/types';
import type { OverlayLabel } from '$lib/presentation/components/lineage/group-label-overlay.svelte';
import { layoutGraph } from '$lib/presentation/_helpers/lineage/layout';
import {
	detectGroupCycles,
	findBackEdges,
	layoutGrouped,
	type GroupBox,
	type GroupLayoutResult
} from '$lib/presentation/_helpers/lineage/group-layout';
import {
	layoutLanes,
	type LaneBand,
	type LaneLayoutResult
} from '$lib/presentation/_helpers/lineage/lane-layout';

export type FlowLayoutOptions = {
	project: Project;
	graph: Graph;
	groupMode: GroupMode;
	compactNodes: boolean;
	selectedIds: Set<string>;
	mutedIds?: Set<string>;
	emphasisIds?: Set<string>;
	notes?: Map<string, { text: string; tone: 'info' | 'warn' }>;
	collapsed: Set<string>;
	groupKeyByNodeId: Map<string, string>;
	viewTargets: Set<string>;
};

export type FlowLayoutResult = {
	nodes: Node[];
	edges: Edge[];
	overlayLabels: OverlayLabel[];
	cycles: [string, string][];
};

type RemappedEdge = {
	id: string;
	source: string;
	target: string;
	type: RefType;
	flowState: GraphEdge['flowState'];
};

type NodeDimensions = { width: number; height: number };

export function groupLabel(key: string): string {
	return key === '__shared_sources__' ? 'shared sources' : key === '__ungrouped__' ? 'ungrouped' : key;
}

export function buildGroupKeyByNodeId(
	project: Project,
	graph: Graph,
	grouped: boolean
): Map<string, string> {
	const map: Map<string, string> = new Map<string, string>();
	if (!grouped) return map;
	const pipelineByModelName: Map<string, string> = new Map(
		project.models.map((model) => [model.name, model.pipeline])
	);
	const visiblePipelines: Set<string> = new Set(
		graph.nodes
			.map((node) => pipelineByModelName.get(node.logicalName))
			.filter((pipeline): pipeline is string => pipeline !== undefined)
	);

	const consumersBySource: Map<string, Set<string>> = new Map<string, Set<string>>();
	for (const model of project.models) {
		for (const ref of model.refs) {
			if (!ref.isSource) continue;
			const bucket: Set<string> = consumersBySource.get(ref.name) ?? new Set<string>();
			bucket.add(model.pipeline);
			consumersBySource.set(ref.name, bucket);
		}
	}

	for (const node of graph.nodes) {
		if (node.logicalType === 'source') {
			const consumers: Set<string> = consumersBySource.get(node.logicalName) ?? new Set<string>();
			const visible: string[] = [...consumers].filter((pipeline) => visiblePipelines.has(pipeline));
			map.set(node.id, visible.length === 1 ? visible[0] : '__shared_sources__');
			continue;
		}
		const pipeline: string | undefined = pipelineByModelName.get(node.logicalName);
		map.set(node.id, pipeline ?? '__ungrouped__');
	}
	return map;
}

export function edgeClass(
	type: RefType,
	flowState: GraphEdge['flowState'],
	dimmed: boolean,
	back: boolean,
	intoView: boolean = false
): string {
	if (dimmed) return 'sb-edge-dimmed';
	const base: string =
		type === 'mutable_reference'
			? 'sb-edge-mutable'
			: type === 'reference'
				? intoView
					? 'sb-edge-view-read'
					: 'sb-edge-reference'
				: flowState === 'flowing'
					? 'sb-edge-driving-flowing'
					: flowState === 'stalled'
						? 'sb-edge-driving-stalled'
						: 'sb-edge-driving';
	return back ? `${base} sb-edge-back` : base;
}

function edgeDomAttributes(
	type: RefType,
	flowState: GraphEdge['flowState']
): Record<string, string> {
	return { 'data-ref-type': type, 'data-flow-state': flowState };
}

function dimensions(compactNodes: boolean): NodeDimensions {
	return { width: compactNodes ? 186 : 248, height: compactNodes ? 56 : 112 };
}

function streamNode(node: GraphNode, options: FlowLayoutOptions): Node {
	return {
		id: node.id,
		type: 'stream',
		position: { x: 0, y: 0 },
		selected: options.selectedIds.has(node.id),
		data: {
			...node,
			compact: options.compactNodes,
			lightweight: options.graph.nodes.length > 150,
			muted: options.mutedIds?.has(node.id) ?? false,
			emphasis: options.emphasisIds?.has(node.id) ?? false,
			note: options.notes?.get(node.id)
		} as unknown as Record<string, unknown>
	};
}

function renderedEdge(
	edge: GraphEdge | RemappedEdge,
	viewTargets: Set<string>,
	back: boolean = false
): Edge {
	return {
		id: edge.id,
		source: edge.source,
		target: edge.target,
		domAttributes: edgeDomAttributes(edge.type, edge.flowState),
		class: edgeClass(edge.type, edge.flowState, false, back, viewTargets.has(edge.target))
	};
}

function overlayLabel(
	box: Pick<GroupBox, 'groupKey' | 'x' | 'y' | 'width'>,
	options: FlowLayoutOptions,
	keyOf: (nodeId: string) => string | undefined,
	collapsible: boolean
): OverlayLabel {
	return {
		groupKey: box.groupKey,
		label: groupLabel(box.groupKey),
		sublabel:
			options.project.pipelines.find((pipeline) => pipeline.name === box.groupKey)?.boundaryMode ??
			null,
		modelCount: options.graph.nodes.filter((node) => keyOf(node.id) === box.groupKey).length,
		x: box.x,
		y: box.y,
		width: box.width,
		collapsible
	};
}

function buildUngrouped(options: FlowLayoutOptions, size: NodeDimensions): FlowLayoutResult {
	const nodes: Node[] = options.graph.nodes.map((node) => streamNode(node, options));
	const edges: Edge[] = options.graph.edges.map((edge) =>
		renderedEdge(edge, options.viewTargets)
	);
	return {
		nodes: layoutGraph(nodes, edges, {
			rankSep: options.compactNodes ? 96 : 150,
			nodeSep: options.compactNodes ? 22 : 30,
			assumedWidth: size.width
		}),
		edges,
		overlayLabels: [],
		cycles: []
	};
}

function buildLanes(options: FlowLayoutOptions, size: NodeDimensions): FlowLayoutResult {
	const keyOf: (nodeId: string) => string | undefined = (nodeId: string): string | undefined =>
		options.groupKeyByNodeId.get(nodeId);
	const laneNodes: Node[] = options.graph.nodes.map((node) => streamNode(node, options));
	const laneEdges: Edge[] = options.graph.edges.map((edge) => ({
		id: edge.id,
		source: edge.source,
		target: edge.target
	}));
	const laid: LaneLayoutResult = layoutLanes(
		laneNodes,
		laneEdges,
		(node) => keyOf(node.id) ?? '__ungrouped__',
		{
			rankSep: options.compactNodes ? 96 : 130,
			nodeSep: options.compactNodes ? 22 : 28,
			assumedWidth: size.width,
			assumedHeight: size.height
		}
	);
	const bands: Node[] = laid.lanes.map((lane) => laneBandNode(lane));
	return {
		nodes: [...bands, ...laid.nodes],
		edges: options.graph.edges.map((edge) => renderedEdge(edge, options.viewTargets)),
		overlayLabels: laid.lanes.map((lane) => overlayLabel(lane, options, keyOf, false)),
		cycles: []
	};
}

function laneBandNode(lane: LaneBand): Node {
	return {
		id: lane.id,
		type: 'lane',
		position: { x: lane.x, y: lane.y },
		width: lane.width,
		height: lane.height,
		selectable: false,
		draggable: false,
		zIndex: -1,
		data: { groupKey: lane.groupKey, index: lane.index } as unknown as Record<string, unknown>
	};
}

function remapEdges(
	edges: GraphEdge[],
	collapsed: Set<string>,
	keyOf: (nodeId: string) => string | undefined
): RemappedEdge[] {
	const remap: (nodeId: string) => string = (nodeId: string): string => {
		const key: string | undefined = keyOf(nodeId);
		return key && collapsed.has(key) ? `collapsed:${key}` : nodeId;
	};
	const seen: Set<string> = new Set<string>();
	const remapped: RemappedEdge[] = [];
	for (const edge of edges) {
		const source: string = remap(edge.source);
		const target: string = remap(edge.target);
		const signature: string = `${source}->${target}`;
		if (source === target || seen.has(signature)) continue;
		seen.add(signature);
		remapped.push({ ...edge, source, target });
	}
	return remapped;
}

function statusCounts(
	nodes: GraphNode[],
	keyOf: (nodeId: string) => string | undefined
): Map<string, Record<ModelStatus, number>> {
	const byGroup: Map<string, Record<ModelStatus, number>> = new Map<
		string,
		Record<ModelStatus, number>
	>();
	for (const node of nodes) {
		const key: string | undefined = keyOf(node.id);
		if (!key) continue;
		const counts: Record<ModelStatus, number> =
			byGroup.get(key) ?? { fresh: 0, lagging: 0, stalled: 0, drift: 0, unknown: 0, source: 0 };
		counts[node.status] += 1;
		byGroup.set(key, counts);
	}
	return byGroup;
}

function collapsedNodes(
	options: FlowLayoutOptions,
	keyOf: (nodeId: string) => string | undefined,
	toggleGroup: (groupKey: string) => void
): Node[] {
	const counts: Map<string, Record<ModelStatus, number>> = statusCounts(options.graph.nodes, keyOf);
	return [...options.collapsed]
		.filter((key) => options.graph.nodes.some((node) => keyOf(node.id) === key))
		.map((key) => ({
			id: `collapsed:${key}`,
			type: 'collapsedGroup',
			position: { x: 0, y: 0 },
			data: {
				groupKey: key,
				label: groupLabel(key),
				sublabel: null,
				modelCount: options.graph.nodes.filter((node) => keyOf(node.id) === key).length,
				countLabel: options.compactNodes ? 'objects' : 'models',
				groupKind:
					key === '__shared_sources__'
						? 'shared sources'
						: key === '__ungrouped__'
							? 'ungrouped'
							: 'pipeline',
				statusCounts: counts.get(key) ?? {},
				ontoggle: toggleGroup
			} as unknown as Record<string, unknown>
		}));
}

function groupContainer(box: GroupBox): Node {
	return {
		id: box.id,
		type: 'group',
		position: { x: box.x, y: box.y },
		width: box.width,
		height: box.height,
		selectable: false,
		draggable: false,
		zIndex: -1,
		data: { groupKey: box.groupKey } as unknown as Record<string, unknown>
	};
}

function positionCollapsedNode(node: Node, boxes: GroupBox[]): Node {
	if (!node.id.startsWith('collapsed:')) return node;
	const box: GroupBox | undefined = boxes.find(
		(candidate) => candidate.groupKey === node.id.slice('collapsed:'.length)
	);
	return {
		...node,
		parentId: undefined,
		extent: undefined,
		position: box ? { x: box.x, y: box.y } : node.position
	};
}

function buildBoxes(
	options: FlowLayoutOptions,
	size: NodeDimensions,
	toggleGroup: (groupKey: string) => void
): FlowLayoutResult {
	const keyOf: (nodeId: string) => string | undefined = (nodeId: string): string | undefined =>
		options.groupKeyByNodeId.get(nodeId);
	const visible: GraphNode[] = options.graph.nodes.filter(
		(node) => !options.collapsed.has(keyOf(node.id) ?? '')
	);
	const remapped: RemappedEdge[] = remapEdges(options.graph.edges, options.collapsed, keyOf);
	const memberNodes: Node[] = visible.map((node) => streamNode(node, options));
	const layoutNodes: Node[] = [...memberNodes, ...collapsedNodes(options, keyOf, toggleGroup)];
	const layoutEdges: Edge[] = remapped.map((edge) => ({
		id: edge.id,
		source: edge.source,
		target: edge.target
	}));
	const laid: GroupLayoutResult = layoutGrouped(
		layoutNodes,
		layoutEdges,
		(node) =>
			node.id.startsWith('collapsed:')
				? node.id.slice('collapsed:'.length)
				: (keyOf(node.id) ?? '__ungrouped__'),
		{
			rankSep: options.compactNodes ? 96 : 130,
			nodeSep: options.compactNodes ? 22 : 28,
			assumedWidth: size.width,
			assumedHeight: size.height
		}
	);
	const groupOfId: (nodeId: string) => string | undefined = (
		nodeId: string
	): string | undefined =>
		nodeId.startsWith('collapsed:') ? nodeId.slice('collapsed:'.length) : keyOf(nodeId);
	const back: Set<string> = findBackEdges(layoutEdges, laid.boxes, groupOfId);
	const containers: Node[] = laid.boxes
		.filter((box) => !options.collapsed.has(box.groupKey))
		.map((box) => groupContainer(box));
	return {
		nodes: [...containers, ...laid.nodes.map((node) => positionCollapsedNode(node, laid.boxes))],
		edges: remapped.map((edge) => renderedEdge(edge, options.viewTargets, back.has(edge.id))),
		overlayLabels: laid.boxes
			.filter((box) => !options.collapsed.has(box.groupKey))
			.map((box) => overlayLabel(box, options, keyOf, true)),
		cycles: detectGroupCycles(layoutEdges, groupOfId)
	};
}

export function buildFlowLayout(
	options: FlowLayoutOptions,
	toggleGroup: (groupKey: string) => void
): FlowLayoutResult {
	const size: NodeDimensions = dimensions(options.compactNodes);
	if (options.groupMode === 'none') return buildUngrouped(options, size);
	if (options.groupMode === 'lanes') return buildLanes(options, size);
	return buildBoxes(options, size, toggleGroup);
}
