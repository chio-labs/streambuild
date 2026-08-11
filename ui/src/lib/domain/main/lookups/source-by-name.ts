import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project, Source } from '$lib/domain/types';

export function sourceByName(project: Project, name: string): Source | undefined {
	return domainDerivations.sourceByName(project, name);
}
