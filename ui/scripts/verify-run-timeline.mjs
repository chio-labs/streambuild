import assert from 'node:assert/strict';

import { createServer } from 'vite';

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' });

try {
	const { buildTimeline } = await vite.ssrLoadModule(
		'/src/routes/runs/[id]/utils/timeline.ts'
	);

	function event(sequence, kind, statementSequence, stepId) {
		return { sequence, event: kind, statementSequence, stepId };
	}

	const liveEvents = [
		event(1, 'run_started'),
		event(2, 'statement_started', 1, 'prepare_orders'),
		event(3, 'statement_completed', 1, 'prepare_orders'),
		event(4, 'run_heartbeat'),
		event(5, 'statement_started', 2, 'replay_orders')
	];
	assert.deepEqual(
		buildTimeline(liveEvents, true).map((item) => item.sequence),
		[5, 3, 1],
		'completed statements collapse to their result while the active statement remains'
	);

	const repeatedAudits = [
		event(1, 'audit_started', undefined, 'freshness'),
		event(2, 'audit_completed', undefined, 'freshness'),
		event(3, 'audit_started', undefined, 'freshness'),
		event(4, 'audit_completed', undefined, 'freshness'),
		event(5, 'audit_started', undefined, 'freshness')
	];
	assert.deepEqual(
		buildTimeline(repeatedAudits, true).map((item) => item.sequence),
		[5, 4, 2],
		'repeated audit names pair one-for-one and leave only the active start'
	);

	const terminalEvents = [
		event(1, 'statement_started', 1, 'prepare_orders'),
		event(2, 'statement_completed', 1, 'prepare_orders'),
		event(3, 'statement_started', 2, 'replay_orders'),
		event(4, 'run_completed')
	];
	assert.deepEqual(
		buildTimeline(terminalEvents, false).map((item) => item.sequence),
		[4, 2],
		'terminal timelines omit both paired and orphaned start rows'
	);

	assert.deepEqual(
		buildTimeline(liveEvents, true, 2).map((item) => item.sequence),
		[5, 3],
		'the limit applies after hidden events are removed'
	);

	console.log('✓ run timeline  completed pairs collapse and active starts remain');
} finally {
	await vite.close();
}
