import { modelsInPipeline } from '$lib/domain/main/lookups/models-in-pipeline';
import { pipelineByName } from '$lib/domain/main/lookups/pipeline-by-name';
import { sourceByName } from '$lib/domain/main/lookups/source-by-name';
import { streamTree } from '$lib/domain/main/pipelines/stream-tree';
import type { PipelineSideReference, PipelineViewSnapshot } from '$lib/pipeline-view/types';
import type { Model, Project } from '$lib/domain/types';

export function buildPipelineSnapshot(project: Project, pipelineName: string): PipelineViewSnapshot {
	const pipeline: PipelineViewSnapshot['pipeline'] = pipelineByName(project, pipelineName);
	const models: Model[] = modelsInPipeline(project, pipelineName);
	const sideReferences: PipelineSideReference[] = [];
	for (const model of models) {
		for (const ref of model.refs) {
			if (ref.type !== 'driving_input') sideReferences.push({ from: model.name, ref });
		}
	}
	return {
		pipeline,
		source: pipeline?.sourceName ? sourceByName(project, pipeline.sourceName) : undefined,
		tree: streamTree(project, pipelineName),
		models,
		sideReferences
	};
}
