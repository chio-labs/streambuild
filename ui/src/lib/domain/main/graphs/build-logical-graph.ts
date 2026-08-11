import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project } from '$lib/domain/types';
import type { Graph } from '$lib/lineage/types';

export function buildLogicalGraph(project: Project): Graph {
	return domainDerivations.buildLogicalGraph(project);
}
