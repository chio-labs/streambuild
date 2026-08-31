import { describe, expect, it } from 'vitest';
import type { Project } from '$lib/domain/types';
import type { Graph, GraphEdge, GraphNode } from '$lib/lineage/types';
import {
	buildFlowLayout,
	buildGroupKeyByNodeId,
	type FlowLayoutResult
} from '$lib/presentation/_helpers/lineage/flow-layout';

const PIPELINE_COUNT = 103;
const PHYSICAL_NODE_COUNT = 828;
const DEFAULT_LAYOUT_BUDGET_MS = 1_000;

function physicalNode(index: number): GraphNode {
	const modelIndex: number = index % PIPELINE_COUNT;
	return {
		id: `rel:physical_${index}`,
		label: `physical_${index}`,
		logicalName: `model_${modelIndex}`,
		logicalType: 'model',
		physicalType: index % 2 === 0 ? 'model_mv' : 'model_table',
		status: 'fresh',
		anchor: null,
		kindLabel: 'TABLE',
		sublabel: null,
		rows: null,
		rowsPerSecond: null,
		failingChecks: 0,
		warningChecks: 0,
		totalChecks: 0,
		drift: false
	};
}

function mustardScaleFixture(): { project: Project; graph: Graph } {
	const nodes: GraphNode[] = Array.from({ length: PHYSICAL_NODE_COUNT }, (_, index) =>
		physicalNode(index)
	);
	const edges: GraphEdge[] = Array.from({ length: PHYSICAL_NODE_COUNT - 1 }, (_, index) => ({
		id: `cross_${index}`,
		source: `rel:physical_${index}`,
		target: `rel:physical_${index + 1}`,
		type: 'driving_input',
		flowState: 'flowing'
	}));
	const project: Project = {
		models: Array.from({ length: PIPELINE_COUNT }, (_, index) => ({
			name: `model_${index}`,
			pipeline: `pipeline_${index}`,
			refs: []
		})),
		pipelines: Array.from({ length: PIPELINE_COUNT }, (_, index) => ({
			name: `pipeline_${index}`,
			boundaryMode: null
		}))
	} as unknown as Project;
	return { project, graph: { nodes, edges } };
}

describe('lineage flow layout', () => {
	it('given a Mustard-scale physical graph when laying out defaults then stays within budget', () => {
		const { project, graph } = mustardScaleFixture();
		const groupKeyByNodeId: Map<string, string> = buildGroupKeyByNodeId(project, graph, true);
		const started: number = performance.now();

		const result: FlowLayoutResult = buildFlowLayout(
			{
				project,
				graph,
				groupMode: 'boxes',
				compactNodes: true,
				selectedIds: new Set(),
				collapsed: new Set(groupKeyByNodeId.values()),
				groupKeyByNodeId,
				viewTargets: new Set()
			},
			() => undefined
		);
		const elapsed: number = performance.now() - started;

		expect(result.nodes).toHaveLength(PIPELINE_COUNT);
		expect(result.nodes.every((node) => node.type === 'collapsedGroup')).toBe(true);
		expect(elapsed).toBeLessThan(DEFAULT_LAYOUT_BUDGET_MS);
	});
});
