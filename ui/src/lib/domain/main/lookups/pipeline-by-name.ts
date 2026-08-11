import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Pipeline, Project } from '$lib/domain/types';

export function pipelineByName(project: Project, name: string): Pipeline | undefined {
	return domainDerivations.pipelineByName(project, name);
}
