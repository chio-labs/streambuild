import { describe, expect, it } from 'vitest';

import type { RunEventFeed } from '$lib/api/types';
import { buildStatementProgressPresentation } from '$lib/run-presentation/main/build-statement-progress-presentation';

type StatementProgress = NonNullable<RunEventFeed['statementProgress']>;

function progress(overrides: Partial<StatementProgress> = {}): StatementProgress {
	return {
		found: true,
		queryId: 'query-1',
		statementSequence: 4,
		stepId: 'replay_orders',
		phase: 'replay',
		observedAt: '2026-08-21 12:00:00',
		readRows: 250,
		totalRowsApprox: 1000,
		readRowsPerSecond: 25,
		...overrides
	};
}

describe('statement progress presentation', () => {
	it('given a credible ClickHouse total when presenting progress then percentage and ETA are shown', () => {
		expect(buildStatementProgressPresentation(progress(), 10)).toEqual({
			position: '4/10',
			pendingStatements: 6,
			percentage: 25,
			etaSeconds: 30
		});
	});

	it('given no credible denominator when presenting progress then percentage and ETA stay indeterminate', () => {
		expect(
			buildStatementProgressPresentation(progress({ totalRowsApprox: 0 }), 10)
		).toMatchObject({ percentage: null, etaSeconds: null });
	});
});
