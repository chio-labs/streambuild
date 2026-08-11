import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project, Source } from '$lib/domain/types';

export function rootSourcesFor(project: Project, modelNames: Iterable<string>): Source[] {
	return domainDerivations.rootSourcesFor(project, modelNames);
}
