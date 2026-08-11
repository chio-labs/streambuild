import { protectedPipelinesForBuild as resolveProtectedPipelines } from '$lib/domain/_helpers/protection';
import type { Pipeline, Project } from '$lib/domain/types';

export function protectedPipelinesForBuild(project: Project, selectors: string[]): Pipeline[] {
	return resolveProtectedPipelines(project, selectors);
}
