/**
 * Two-phase compound layout: lay out each group internally, then lay out the
 * graph OF groups, then offset each group's children into place.
 *
 * dagre has no compound/cluster support, so this is the standard workaround.
 *
 * On cycles: StreamBuild's MODEL graph is a DAG, but collapsing it can produce a
 * cycle in the group graph — `a1 → b1 → a2` with a1,a2 ∈ A and b1 ∈ B is a legal
 * chain yet yields A→B and B→A. dagre handles that itself (its `acyclic` phase
 * reverses cycle edges, ranks, then restores true direction), so nothing here
 * deletes or hides an edge. One box simply ends up left of a box it depends on.
 * `detectGroupCycles` exists purely so the UI can say so out loud.
 */

import dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/svelte';

/** Padding inside a group box; top is larger to clear the header. */
/** Height of the group header tab. Body content starts below it. */
export const GROUP_HEADER_HEIGHT = 34;

export const GROUP_PADDING = { top: GROUP_HEADER_HEIGHT + 16, right: 22, bottom: 20, left: 20 };

const DEFAULT_NODE_WIDTH = 248;
const DEFAULT_NODE_HEIGHT = 112;

export type GroupLayoutOptions = {
	/** Gap between ranks inside a group. */
	rankSep?: number;
	/** Gap between nodes within a rank. */
	nodeSep?: number;
	/** Gap between ranks of the group-level graph. */
	groupRankSep?: number;
	/** Gap between groups within a rank. */
	groupNodeSep?: number;
	assumedWidth?: number;
	assumedHeight?: number;
};

export type GroupBox = {
	id: string;
	groupKey: string;
	x: number;
	y: number;
	width: number;
	height: number;
};

export type GroupLayoutResult = {
	/** Child nodes, positioned RELATIVE to their parent group. */
	nodes: Node[];
	boxes: GroupBox[];
};

function sizeOf(node: Node, opts: GroupLayoutOptions): { width: number; height: number } {
	return {
		width: node.measured?.width ?? (node.width as number) ?? opts.assumedWidth ?? DEFAULT_NODE_WIDTH,
		height:
			node.measured?.height ?? (node.height as number) ?? opts.assumedHeight ?? DEFAULT_NODE_HEIGHT
	};
}

/** `group:<key>` — the Svelte Flow node id for a group container. */
export function groupNodeId(groupKey: string): string {
	return `group:${groupKey}`;
}

/**
 * @param groupOf maps a node id to its group key. Nodes with no group are placed
 *                in a synthetic group of their own so they still participate in
 *                the group-level ranking rather than piling up at the origin.
 */
export function layoutGrouped(
	nodes: Node[],
	edges: Edge[],
	groupOf: (node: Node) => string,
	opts: GroupLayoutOptions = {}
): GroupLayoutResult {
	const groupKeyByNode = new Map<string, string>();
	const membersByGroup = new Map<string, Node[]>();

	for (const node of nodes) {
		const key: string = groupOf(node);
		groupKeyByNode.set(node.id, key);
		const bucket: Node[] = membersByGroup.get(key) ?? [];
		bucket.push(node);
		membersByGroup.set(key, bucket);
	}

	// ── phase 1: lay out each group internally ────────────────────────────────
	const innerPositions = new Map<string, { x: number; y: number }>();
	const groupSize = new Map<string, { width: number; height: number }>();

	for (const [key, members] of membersByGroup) {
		const inner = new dagre.graphlib.Graph();
		inner.setGraph({
			rankdir: 'LR',
			ranksep: opts.rankSep ?? 110,
			nodesep: opts.nodeSep ?? 26,
			marginx: 0,
			marginy: 0
		});
		inner.setDefaultEdgeLabel(() => ({}));

		const memberIds = new Set(members.map((node) => node.id));
		for (const node of members) {
			const { width, height } = sizeOf(node, opts);
			inner.setNode(node.id, { width, height });
		}
		for (const edge of edges) {
			if (memberIds.has(edge.source) && memberIds.has(edge.target)) {
				inner.setEdge(edge.source, edge.target);
			}
		}

		dagre.layout(inner);

		let minX = Infinity;
		let minY = Infinity;
		let maxX = -Infinity;
		let maxY = -Infinity;

		for (const node of members) {
			const pos = inner.node(node.id);
			const { width, height } = sizeOf(node, opts);
			const left: number = pos.x - width / 2;
			const top: number = pos.y - height / 2;
			innerPositions.set(node.id, { x: left, y: top });
			minX = Math.min(minX, left);
			minY = Math.min(minY, top);
			maxX = Math.max(maxX, left + width);
			maxY = Math.max(maxY, top + height);
		}

		// Normalise so the group's own content starts at the padding origin.
		for (const node of members) {
			const pos = innerPositions.get(node.id) as { x: number; y: number };
			innerPositions.set(node.id, {
				x: pos.x - minX + GROUP_PADDING.left,
				y: pos.y - minY + GROUP_PADDING.top
			});
		}

		groupSize.set(key, {
			width: maxX - minX + GROUP_PADDING.left + GROUP_PADDING.right,
			height: maxY - minY + GROUP_PADDING.top + GROUP_PADDING.bottom
		});
	}

	// ── phase 2: lay out the graph OF groups ──────────────────────────────────
	const outer = new dagre.graphlib.Graph();
	outer.setGraph({
		rankdir: 'LR',
		ranksep: opts.groupRankSep ?? 90,
		nodesep: opts.groupNodeSep ?? 44,
		marginx: 28,
		marginy: 28
	});
	outer.setDefaultEdgeLabel(() => ({}));

	for (const [key, size] of groupSize) {
		outer.setNode(key, { width: size.width, height: size.height });
	}

	const seen = new Set<string>();
	for (const edge of edges) {
		const from: string | undefined = groupKeyByNode.get(edge.source);
		const to: string | undefined = groupKeyByNode.get(edge.target);
		if (!from || !to || from === to) continue;
		const signature = `${from}->${to}`;
		if (seen.has(signature)) continue;
		seen.add(signature);
		// dagre's acyclic phase deals with any cycle here; we never drop the edge.
		outer.setEdge(from, to);
	}

	dagre.layout(outer);

	// ── phase 3: offset children into their group ─────────────────────────────
	const boxes: GroupBox[] = [];
	for (const [key, size] of groupSize) {
		const pos = outer.node(key);
		boxes.push({
			id: groupNodeId(key),
			groupKey: key,
			x: pos.x - size.width / 2,
			y: pos.y - size.height / 2,
			width: size.width,
			height: size.height
		});
	}

	const positioned: Node[] = nodes.map((node) => ({
		...node,
		// Positions are relative to the parent group node.
		position: innerPositions.get(node.id) ?? { x: 0, y: 0 },
		parentId: groupNodeId(groupKeyByNode.get(node.id) as string),
		extent: 'parent' as const
	}));

	return { nodes: positioned, boxes };
}

/**
 * Pairs of groups that reference each other. Purely for disclosure — the layout
 * copes regardless, but an edge flowing right-to-left looks like a bug unless
 * the UI says why.
 */
export function detectGroupCycles(
	edges: Edge[],
	groupOfId: (nodeId: string) => string | undefined
): [string, string][] {
	const adjacency = new Map<string, Set<string>>();
	for (const edge of edges) {
		const from: string | undefined = groupOfId(edge.source);
		const to: string | undefined = groupOfId(edge.target);
		if (!from || !to || from === to) continue;
		const bucket: Set<string> = adjacency.get(from) ?? new Set<string>();
		bucket.add(to);
		adjacency.set(from, bucket);
	}

	const pairs: [string, string][] = [];
	for (const [from, targets] of adjacency) {
		for (const to of targets) {
			if (from < to && adjacency.get(to)?.has(from)) pairs.push([from, to]);
		}
	}
	return pairs;
}

/**
 * Cross-group edges that run against the group ranking, i.e. right-to-left. They
 * are drawn with their true direction but routed differently so they read as
 * deliberate rather than tangled.
 */
export function findBackEdges(
	edges: Edge[],
	boxes: GroupBox[],
	groupOfId: (nodeId: string) => string | undefined
): Set<string> {
	const xByGroup = new Map<string, number>();
	for (const box of boxes) xByGroup.set(box.groupKey, box.x);

	const back = new Set<string>();
	for (const edge of edges) {
		const from: string | undefined = groupOfId(edge.source);
		const to: string | undefined = groupOfId(edge.target);
		if (!from || !to || from === to) continue;
		const fromX: number | undefined = xByGroup.get(from);
		const toX: number | undefined = xByGroup.get(to);
		if (fromX === undefined || toX === undefined) continue;
		if (toX < fromX) back.add(edge.id);
	}
	return back;
}
