import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestAuditBatchRun, requestCheckRun, requestCheckStatuses } from '$lib/api/_api/quality';
import type { CheckRunResult, CheckStatusRecord } from '$lib/api/types';

describe('quality API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given quality operations when requested then status reads and check runs use typed transport contracts', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValueOnce(new Response('[]'))
			.mockResolvedValueOnce(new Response('{"passed":true}'))
			.mockResolvedValueOnce(new Response('[{"name":"fresh_orders","passed":true}]'));
		vi.stubGlobal('fetch', fetchMock);

		const statuses: CheckStatusRecord[] = await requestCheckStatuses();
		const result: CheckRunResult = await requestCheckRun('audit', 'fresh_orders');
		const batchResult: (CheckRunResult & { name: string })[] = await requestAuditBatchRun([
			'fresh_orders',
			'valid_customers'
		]);

		expect(statuses).toEqual([]);
		expect(result).toEqual({ passed: true });
		expect(batchResult).toEqual([{ name: 'fresh_orders', passed: true }]);
		expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/checks/status');
		expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/checks/run', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ kind: 'audit', name: 'fresh_orders' })
		});
		expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/audits/run', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ names: ['fresh_orders', 'valid_customers'] })
		});
	});
});
