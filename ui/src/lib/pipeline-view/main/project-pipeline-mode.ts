import type { Project } from '$lib/domain/types';

export type ProjectPipelineMode = Project['pipelines'][number]['mode'] | 'mixed' | 'unknown';

export function projectPipelineMode(project: Project): ProjectPipelineMode {
	const modes: Set<Project['pipelines'][number]['mode']> = new Set(
		project.pipelines.map((pipeline) => pipeline.mode)
	);
	if (modes.size === 0) return 'unknown';
	if (modes.size > 1) return 'mixed';
	return modes.values().next().value ?? 'unknown';
}
