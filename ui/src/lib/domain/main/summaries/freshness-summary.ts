import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project } from '$lib/domain/types';

export function freshnessSummary(
	project: Project
): ReturnType<typeof domainDerivations.freshnessSummary> {
	return domainDerivations.freshnessSummary(project);
}
