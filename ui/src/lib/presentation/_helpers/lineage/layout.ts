import dagre, { type Graph as DagreGraph } from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/svelte';

// Fallback dimensions used before a node has been measured by Svelte Flow.
const DEFAULT_WIDTH = 262;
const DEFAULT_HEIGHT = 78;

export type LayoutOptions = {
	/** gap between layers (columns) in LR mode */
	rankSep?: number;
	/** gap between nodes within a layer */
	nodeSep?: number;
	/**
	 * Width to assume before Svelte Flow has measured anything. The physical graph
	 * uses narrower nodes, and without this the first layout over-spaces them.
	 */
	assumedWidth?: number;
};

/**
 * Layered left-to-right layout via dagre. Uses each node's measured size when
 * available (so taller nodes — e.g. with extra Node fields enabled — get the
 * right spacing and the graph reflows cleanly on toggle).
 */
export function layoutGraph(nodes: Node[], edges: Edge[], opts: LayoutOptions = {}): Node[] {
	const g: DagreGraph = new dagre.graphlib.Graph();
	g.setGraph({
		rankdir: 'LR',
		ranksep: opts.rankSep ?? 130,
		nodesep: opts.nodeSep ?? 34,
		marginx: 24,
		marginy: 24
	});
	g.setDefaultEdgeLabel(() => ({}));

	const fallbackWidth: number = opts.assumedWidth ?? DEFAULT_WIDTH;

	for (const node of nodes) {
		const width: number = node.measured?.width ?? (node.width as number) ?? fallbackWidth;
		const height: number = node.measured?.height ?? (node.height as number) ?? DEFAULT_HEIGHT;
		g.setNode(node.id, { width, height });
	}
	for (const edge of edges) {
		g.setEdge(edge.source, edge.target);
	}

	dagre.layout(g);

	return nodes.map((node) => {
		const pos: { x: number; y: number } = g.node(node.id);
		const width: number = node.measured?.width ?? (node.width as number) ?? fallbackWidth;
		const height: number = node.measured?.height ?? (node.height as number) ?? DEFAULT_HEIGHT;
		// dagre returns center coordinates; Svelte Flow expects top-left.
		return {
			...node,
			position: { x: pos.x - width / 2, y: pos.y - height / 2 }
		};
	});
}
