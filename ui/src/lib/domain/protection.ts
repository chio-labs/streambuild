import type { Pipeline, Project } from '$lib/domain/types';

/** Resolve protected pipelines touched by the same downstream closure as `stb build`. */
export function protectedPipelinesForBuild(project: Project, selectors: string[]): Pipeline[] {
	const executionModels = new Set<string>();
	if (selectors.length === 0) {
		for (const model of project.models) executionModels.add(model.name);
	} else {
		for (const selector of selectors) {
			if (selector.startsWith('pipeline:')) {
				const pipeline = project.pipelines.find(
					(item) => item.name === selector.slice('pipeline:'.length)
				);
				for (const model of pipeline?.models ?? []) executionModels.add(model);
			} else if (project.models.some((model) => model.name === selector)) {
				executionModels.add(selector);
			}
		}
	}

	let changed = true;
	while (changed) {
		changed = false;
		for (const model of project.models) {
			if (
				!executionModels.has(model.name) &&
				model.refs.some((ref) => !ref.isSource && executionModels.has(ref.name))
			) {
				executionModels.add(model.name);
				changed = true;
			}
		}
	}

	return project.pipelines.filter(
		(pipeline) =>
			pipeline.protection !== null && pipeline.models.some((model) => executionModels.has(model))
	);
}
