import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Model, Project } from '$lib/domain/types';

export function modelsInPipeline(project: Project, pipelineName: string): Model[] {
	return domainDerivations.modelsInPipeline(project, pipelineName);
}
