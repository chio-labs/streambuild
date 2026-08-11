import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project } from '$lib/domain/types';

export function streamTree(
	project: Project,
	pipelineName: string
): ReturnType<typeof domainDerivations.streamTree> {
	return domainDerivations.streamTree(project, pipelineName);
}
