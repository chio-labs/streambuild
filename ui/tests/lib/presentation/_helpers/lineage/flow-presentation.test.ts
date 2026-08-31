import { describe, expect, it } from 'vitest';
import type { Edge, Node } from '@xyflow/svelte';
import type { GraphEdge, GraphNode } from '$lib/lineage/types';
import {
	graphTopologyKey,
	refreshFlowPresentation,
	type FlowPresentationResult
} from '$lib/presentation/_helpers/lineage/flow-presentation';

function graphNode(overrides: Partial<GraphNode> = {}): GraphNode {
	return {
		id: 'model:orders',
		label: 'orders',
		logicalName: 'orders',
		logicalType: 'model',
		physicalType: null,
		status: 'fresh',
		anchor: null,
		kindLabel: 'TABLE',
		sublabel: null,
		rows: 10,
		rowsPerSecond: null,
		failingChecks: 0,
		warningChecks: 0,
		totalChecks: 0,
		drift: false,
		...overrides
	};
}

function graphEdge(overrides: Partial<GraphEdge> = {}): GraphEdge {
	return {
		id: 'source:events->model:orders',
		source: 'source:events',
		target: 'model:orders',
		type: 'driving_input',
		flowState: 'unknown',
		...overrides
	};
}

describe('lineage flow presentation', () => {
	it('given live status changes when fingerprinting topology then keeps the layout key stable', () => {
		const originalNode: GraphNode = graphNode();
		const originalEdge: GraphEdge = graphEdge();

		const original: string = graphTopologyKey([originalNode], [originalEdge]);
		const updated: string = graphTopologyKey(
			[graphNode({ status: 'stalled', rows: 20 })],
			[graphEdge({ flowState: 'stalled' })]
		);

		expect(updated).toBe(original);
	});

	it('given definition changes when fingerprinting topology then invalidates the layout key', () => {
		const original: string = graphTopologyKey([graphNode()], [graphEdge()]);
		const updated: string = graphTopologyKey(
			[graphNode({ label: 'renamed orders', logicalName: 'renamed_orders' })],
			[graphEdge()]
		);

		expect(updated).not.toBe(original);
	});

	it('given positioned flow elements when live status changes then preserves geometry', () => {
		const node: Node = {
			id: 'model:orders',
			type: 'stream',
			position: { x: 120, y: 80 },
			data: { ...graphNode() }
		};
		const edge: Edge = {
			id: 'source:events->model:orders',
			source: 'source:events',
			target: 'model:orders',
			class: 'sb-edge-driving',
			data: {},
			domAttributes: { 'data-flow-state': 'unknown' }
		};
		const updatedNode: GraphNode = graphNode({ status: 'stalled', rows: 20 });
		const updatedEdge: GraphEdge = graphEdge({ flowState: 'stalled' });

		const result: FlowPresentationResult = refreshFlowPresentation({
			nodes: [node],
			edges: [edge],
			domainNodes: new Map([[updatedNode.id, updatedNode]]),
			domainEdges: new Map([[updatedEdge.id, updatedEdge]]),
			groupKeyByNodeId: new Map([[updatedNode.id, 'orders']]),
			viewTargets: new Set(),
			litEdgeIds: null
		});

		expect(result.nodes[0].position).toEqual({ x: 120, y: 80 });
		expect(result.nodes[0].data.status).toBe('stalled');
		expect(result.nodes[0].data.rows).toBe(20);
		expect(result.edges[0].class).toContain('sb-edge-driving-stalled');
		expect(result.edges[0].domAttributes?.['data-flow-state']).toBe('stalled');
	});
});
