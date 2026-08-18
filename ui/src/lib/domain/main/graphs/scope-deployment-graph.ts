import { buildLogicalGraph } from '$lib/domain/main/graphs/build-logical-graph';
import type { DeploymentDetail, Project } from '$lib/domain/types';
import type { Graph } from '$lib/lineage/types';

type DeploymentModel = DeploymentDetail['models'][number];

interface ScopeDeploymentGraphArgs {
	project: Project;
	deploymentModels: DeploymentModel[];
	modelByRelation: Map<string, string>;
	modelNames: Set<string>;
}

function relationLabel(relation: string | null): string {
	return relation ?? '—';
}

/**
 * Narrow the project graph to a deployment plus one hop upstream, rewriting each
 * node's sublabel to its physical switchover. Pure so the page stays under budget
 * and the transform is unit-testable in isolation.
 */
export function scopeDeploymentGraph({
	project,
	deploymentModels,
	modelByRelation,
	modelNames
}: ScopeDeploymentGraphArgs): Graph {
	const full: Graph = buildLogicalGraph(project);
	const comparisonByModel: Map<string, DeploymentModel> = new Map();
	for (const model of deploymentModels) {
		const name: string | undefined = modelByRelation.get(model.logicalName);
		if (name !== undefined) comparisonByModel.set(name, model);
	}

	const keep: Set<string> = new Set();
	for (const node of full.nodes) {
		if (node.logicalType !== 'source' && modelNames.has(node.logicalName)) keep.add(node.id);
	}
	for (const edge of full.edges) {
		if (keep.has(edge.target)) keep.add(edge.source);
	}

	return {
		nodes: full.nodes
			.filter((node) => keep.has(node.id))
			.map((node) => {
				const comparison: DeploymentModel | undefined = comparisonByModel.get(node.logicalName);
				if (comparison === undefined) return node;
				return {
					...node,
					sublabel: comparison.isNew
						? `new · ${relationLabel(comparison.stagedRelation)}`
						: `${relationLabel(comparison.liveRelation)} → ${relationLabel(comparison.stagedRelation)}`,
					rows: comparison.stagedRows
				};
			}),
		edges: full.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target))
	};
}
