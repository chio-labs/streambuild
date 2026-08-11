import assert from 'node:assert/strict';

import { createServer } from 'vite';

const vite = await createServer({
	optimizeDeps: { noDiscovery: true },
	server: { middlewareMode: true },
	appType: 'custom'
});

try {
	const { domainDerivations } = await vite.ssrLoadModule('/src/lib/domain/_helpers/derive.ts');
	const { modelFlowState } = domainDerivations;
	const table = (state) => ({ kind: 'table', live: { activity: { state } } });

	assert.equal(modelFlowState(table('moving')), 'flowing');
	assert.equal(modelFlowState(table('stalled')), 'stalled');
	assert.equal(modelFlowState(table('idle')), 'unknown');
	assert.equal(modelFlowState(table('unknown')), 'unknown');
	assert.equal(modelFlowState({ kind: 'view', live: { activity: { state: 'moving' } } }), 'unknown');

	console.log('✓ lineage activity  moving, stalled, idle, unknown, and views remain distinct');
} finally {
	await vite.close();
}
