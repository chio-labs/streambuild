import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Model, Project, Source } from '$lib/domain/types';

export function rootSourceFor(project: Project, model: Model): Source | undefined {
	return domainDerivations.rootSourceFor(project, model);
}
