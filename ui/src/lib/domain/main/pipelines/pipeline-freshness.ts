import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project } from '$lib/domain/types';

export function pipelineFreshness(
	project: Project,
	pipelineName: string
): ReturnType<typeof domainDerivations.pipelineFreshness> {
	return domainDerivations.pipelineFreshness(project, pipelineName);
}
