import { describe, expect, it } from 'vitest';
import { buildRunActivity } from '$lib/run-presentation/_helpers/run-activity';
import type { Project } from '$lib/domain/types';
import type { RunActivityPresentation, RunPresentationInput } from '$lib/run-presentation/types';

describe('buildRunActivity', () => {
	it('given a completed audit run when building activity then counts completed audits', () => {
		const input: RunPresentationInput = {
			project: {} as unknown as Project,
			events: [
				{
					sequence: 1,
					emittedAt: '2026-08-22 04:04:20.000',
					event: 'run_started',
					stepId: null,
					phase: null,
					command: 'audit',
					totalStatements: 2
				},
				{
					sequence: 2,
					emittedAt: '2026-08-22 04:04:21.000',
					event: 'audit_completed',
					stepId: 'required fields',
					phase: 'audit',
					status: 'passed'
				},
				{
					sequence: 3,
					emittedAt: '2026-08-22 04:04:22.000',
					event: 'audit_completed',
					stepId: 'unique offsets',
					phase: 'audit',
					status: 'warning'
				}
			],
			running: false,
			status: 'succeeded',
			commandLine: 'audit',
			record: null,
			nowMs: Date.parse('2026-08-22T04:04:22Z')
		};

		const activity: RunActivityPresentation = buildRunActivity(input);

		expect(activity.completedStatements).toHaveLength(2);
		expect(activity.statementSummary).toBe('2/2');
	});
});
