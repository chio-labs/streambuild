import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project } from '$lib/domain/types';

export function projectHealthSummary(
	project: Project
): ReturnType<typeof domainDerivations.projectHealthSummary> {
	return domainDerivations.projectHealthSummary(project);
}
