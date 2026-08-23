import { describe, expect, it } from 'vitest';

import { projectPipelineMode } from '$lib/pipeline-view/main/project-pipeline-mode';
import type { Pipeline, Project } from '$lib/domain/types';

interface ProjectPipelineModeTestCase {
	readonly description: string;
	readonly modes: Pipeline['mode'][];
	readonly expectedMode: 'direct' | 'virtual' | 'mixed' | 'unknown';
}

function projectWithModes(...modes: Pipeline['mode'][]): Project {
	return {
		pipelines: modes.map((mode, index) => ({ name: `pipeline-${index}`, mode }))
	} as Project;
}

describe('project pipeline mode', () => {
	it.each<ProjectPipelineModeTestCase>([
		{ description: 'one direct pipeline resolves direct', modes: ['direct'], expectedMode: 'direct' },
		{
			description: 'matching virtual pipelines resolve virtual',
			modes: ['virtual', 'virtual'],
			expectedMode: 'virtual'
		},
		{
			description: 'different pipeline modes resolve mixed',
			modes: ['direct', 'virtual'],
			expectedMode: 'mixed'
		},
		{ description: 'no pipelines resolve unknown', modes: [], expectedMode: 'unknown' }
	])('$description', (testCase) => {
		expect(projectPipelineMode(projectWithModes(...testCase.modes))).toBe(testCase.expectedMode);
	});
});
