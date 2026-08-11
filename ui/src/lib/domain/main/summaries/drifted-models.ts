import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Model, Project } from '$lib/domain/types';

export function driftedModels(project: Project): Model[] {
	return domainDerivations.driftedModels(project);
}
