import { describe, expect, it } from 'vitest';

import type { RunEvent } from '$lib/api/types';
import { labelRunEvent, labelRunStepId } from '$lib/run-presentation/_helpers/run-event-label';
import { labelRunPhase } from '$lib/run-presentation/_helpers/run-phase-label';
import type { RunEventLabelContext } from '$lib/run-presentation/types';

const context: RunEventLabelContext = {
	displayCommand: 'stb destroy pipelines',
	metadataPreparationCount: 0,
	metadataMigrationCount: 0,
	candidateMetadataCount: 0,
	publicationCount: 0,
	reconcileCount: 0
};

function event(displayName: string | null): RunEvent {
	return {
		sequence: 1,
		emittedAt: '2026-08-25T14:30:00Z',
		event: 'statement_completed',
		stepId: 'destroy_relation_0101',
		displayName,
		phase: 'teardown'
	};
}

describe('destruction run labels', () => {
	it('given a current destruction event when labeling then shows the affected relation', () => {
		expect(labelRunEvent(event('Drop table default.market__tbl_prices__betfair'), context)).toBe(
			'Drop table default.market__tbl_prices__betfair'
		);
		expect(labelRunPhase('teardown')).toBe('remove');
	});

	it('given a historical destruction event when labeling then hides the internal step identifier', () => {
		expect(labelRunEvent(event(null), context)).toBe('Drop relation (101)');
		expect(labelRunStepId('destroy_relation_0101')).toBe('Drop relation (101)');
	});
});
