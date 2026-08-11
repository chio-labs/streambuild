import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project } from '$lib/domain/types';

export function anchorCount(project: Project, pipelineName: string): number {
	return domainDerivations.anchorCount(project, pipelineName);
}
