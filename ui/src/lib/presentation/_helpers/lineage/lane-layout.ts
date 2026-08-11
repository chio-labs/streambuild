/**
 * Lane layout — the alternative to compound boxes.
 *
 * The point of lanes (versus boxes without borders) is that **x comes from a
 * GLOBAL rank**, so the left-to-right flow stays aligned across every pipeline:
 * every pipeline's source sits in the same column, every first model in the next,
 * and so on. Y is then assigned within the pipeline's own horizontal band.
 *
 * Trade-off versus boxes, for the record:
 *  + shared flow axis makes cross-pipeline position comparable
 *  + no nesting, so cross-pipeline edges never pierce a container
 *  − lane height is proportional to content, so a 1-model pipeline beside a
 *    40-model one gives a sliver next to a slab
 *  − no collapse equivalent
 *  − the band is defined by boundaries + a gutter label, both of which degrade
 *    when zoomed out
 */

import dagre, { type Graph as DagreGraph } from '@dagrejs/dagre';
import { orderLanes, weightKey, type LaneWeights } from '$lib/presentation/_helpers/lineage/lane-order';
import type { Node, Edge } from '@xyflow/svelte';

export const LANE_PADDING = { top: 34, bottom: 16, left: 16, right: 16 };
const LANE_ROW_GAP = 18;

export type LaneBand = {
	id: string;
	groupKey: string;
	x: number;
	y: number;
	width: number;
	height: number;
	index: number;
};

export type LaneLayoutResult = {
	nodes: Node[];
	lanes: LaneBand[];
};

export type LaneLayoutOptions = {
	rankSep?: number;
	nodeSep?: number;
	assumedWidth?: number;
	assumedHeight?: number;
};

function sizeOf(node: Node, opts: LaneLayoutOptions): { width: number; height: number } {
	return {
		width: node.measured?.width ?? (node.width as number) ?? opts.assumedWidth ?? 248,
		height: node.measured?.height ?? (node.height as number) ?? opts.assumedHeight ?? 112
	};
}

export function laneNodeId(groupKey: string): string {
	return `lane:${groupKey}`;
}

export function layoutLanes(
	nodes: Node[],
	edges: Edge[],
	groupOf: (node: Node) => string,
	opts: LaneLayoutOptions = {}
): LaneLayoutResult {
	// ── phase 1: global ranking gives every node its x ────────────────────────
	const graph: DagreGraph = new dagre.graphlib.Graph();
	graph.setGraph({
		rankdir: 'LR',
		ranksep: opts.rankSep ?? 130,
		nodesep: opts.nodeSep ?? 28,
		marginx: 24,
		marginy: 24
	});
	graph.setDefaultEdgeLabel(() => ({}));

	for (const node of nodes) {
		const { width, height } = sizeOf(node, opts);
		graph.setNode(node.id, { width, height });
	}
	const ids: Set<string> = new Set(nodes.map((node) => node.id));
	for (const edge of edges) {
		if (ids.has(edge.source) && ids.has(edge.target)) graph.setEdge(edge.source, edge.target);
	}
	dagre.layout(graph);

	const xById = new Map<string, number>();
	for (const node of nodes) {
		const pos: { x: number; y: number } = graph.node(node.id);
		const { width } = sizeOf(node, opts);
		xById.set(node.id, pos.x - width / 2);
	}

	// ── phase 2: bucket into lanes, ordered by their leftmost member ──────────
	const membersByGroup = new Map<string, Node[]>();
	for (const node of nodes) {
		const key: string = groupOf(node);
		const bucket: Node[] = membersByGroup.get(key) ?? [];
		bucket.push(node);
		membersByGroup.set(key, bucket);
	}

	// Depth-sorted seed: how the lanes would read if only dependency order
	// mattered. Used as the tie-break and orientation reference below.
	const depthSeed: string[] = [...membersByGroup.keys()].sort((a, b) => {
		const minA: number = Math.min(
			...(membersByGroup.get(a) ?? []).map((n) => xById.get(n.id) ?? 0)
		);
		const minB: number = Math.min(
			...(membersByGroup.get(b) ?? []).map((n) => xById.get(n.id) ?? 0)
		);
		if (minA !== minB) return minA - minB;
		return a.localeCompare(b);
	});

	// Reorder so heavily connected pipelines end up adjacent, which shortens the
	// cross-lane edges. Depth alone ignores connections entirely and strands
	// pipelines away from the ones feeding them.
	const groupById = new Map<string, string>(nodes.map((node) => [node.id, groupOf(node)]));
	const weights: LaneWeights = new Map();
	for (const edge of edges) {
		const from: string | undefined = groupById.get(edge.source);
		const to: string | undefined = groupById.get(edge.target);
		if (from === undefined || to === undefined || from === to) continue;
		const key: string = weightKey(from, to);
		weights.set(key, (weights.get(key) ?? 0) + 1);
	}

	const orderedGroups: string[] = orderLanes(depthSeed, weights);

	// ── phase 3: y within each lane, packing rows so nodes never overlap ──────
	const positioned: Node[] = [];
	const lanes: LaneBand[] = [];

	let cursorY: number = 0;
	let globalMinX: number = Infinity;
	let globalMaxX: number = -Infinity;

	orderedGroups.forEach((key, index) => {
		const members: Node[] = (membersByGroup.get(key) ?? []).slice().sort(
			(a, b) => (xById.get(a.id) ?? 0) - (xById.get(b.id) ?? 0)
		);

		// Greedy row packing: first row with no horizontal overlap.
		const rows: { right: number }[] = [];
		const rowOf = new Map<string, number>();
		for (const node of members) {
			const { width } = sizeOf(node, opts);
			const left: number = xById.get(node.id) ?? 0;
			let row: number = rows.findIndex((candidate) => candidate.right + opts.nodeSep! <= left);
			if (row === -1) {
				rows.push({ right: left + width });
				row = rows.length - 1;
			} else {
				rows[row].right = left + width;
			}
			rowOf.set(node.id, row);
		}

		const rowHeight: number = (opts.assumedHeight ?? 112) + LANE_ROW_GAP;
		const laneHeight: number =
			Math.max(rows.length, 1) * rowHeight - LANE_ROW_GAP + LANE_PADDING.top + LANE_PADDING.bottom;

		let laneMinX: number = Infinity;
		let laneMaxX: number = -Infinity;

		for (const node of members) {
			const { width } = sizeOf(node, opts);
			const left: number = xById.get(node.id) ?? 0;
			const row: number = rowOf.get(node.id) ?? 0;
			positioned.push({
				...node,
				position: { x: left, y: cursorY + LANE_PADDING.top + row * rowHeight }
			});
			laneMinX = Math.min(laneMinX, left);
			laneMaxX = Math.max(laneMaxX, left + width);
		}

		globalMinX = Math.min(globalMinX, laneMinX);
		globalMaxX = Math.max(globalMaxX, laneMaxX);

		lanes.push({
			id: laneNodeId(key),
			groupKey: key,
			x: 0,
			y: cursorY,
			width: 0,
			height: laneHeight,
			index
		});

		cursorY += laneHeight;
	});

	// Bands span the full graph width so they read as continuous rows.
	for (const lane of lanes) {
		lane.x = globalMinX - LANE_PADDING.left;
		lane.width = globalMaxX - globalMinX + LANE_PADDING.left + LANE_PADDING.right;
	}

	return { nodes: positioned, lanes };
}
