import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Project, SqlTest } from '$lib/domain/types';

export function testsForModel(project: Project, modelName: string): SqlTest[] {
	return domainDerivations.testsForModel(project, modelName);
}
