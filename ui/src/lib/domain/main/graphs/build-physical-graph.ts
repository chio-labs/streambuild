import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Deployment, Project } from '$lib/domain/types';
import type { Graph } from '$lib/lineage/types';

export function buildPhysicalGraph(project: Project, deployments: Deployment[] = []): Graph {
	return domainDerivations.buildPhysicalGraph(project, deployments);
}
