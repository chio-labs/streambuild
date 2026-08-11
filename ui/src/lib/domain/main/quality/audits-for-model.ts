import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Audit, Project } from '$lib/domain/types';

export function auditsForModel(project: Project, modelName: string): Audit[] {
	return domainDerivations.auditsForModel(project, modelName);
}
