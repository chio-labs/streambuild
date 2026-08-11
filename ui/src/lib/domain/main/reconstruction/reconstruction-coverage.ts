import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project, ReconstructionCoverage } from '$lib/domain/types';

export function reconstructionCoverage(project: Project): ReconstructionCoverage[] {
	return domainDerivations.reconstructionCoverage(project);
}
