import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Model, Project } from '$lib/domain/types';

export function modelByName(project: Project, name: string): Model | undefined {
	return domainDerivations.modelByName(project, name);
}
