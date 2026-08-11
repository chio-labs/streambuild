import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchAuditScheduler } from '$lib/quality-monitoring/_api/fetch-audit-scheduler';
import type { AuditSchedulerPayload } from '$lib/quality-monitoring/types';

describe('audit scheduler API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given scheduler payload when requested then typed scheduler state is returned', async () => {
		const payload: AuditSchedulerPayload = {
			enabled: true,
			state: 'idle',
			warehouseNow: '2026-08-11 12:00:00',
			dueCount: 0,
			audits: [],
			health: {
				state: 'idle',
				consecutiveErrors: 0,
				latestError: null,
				backoffSeconds: 0,
				nextTickSeconds: 10,
				lastSuccessfulTick: null,
				runningAuditCount: 0
			}
		};
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)));
		vi.stubGlobal('fetch', fetchMock);

		const result: AuditSchedulerPayload = await fetchAuditScheduler();

		expect(result).toEqual(payload);
		expect(fetchMock).toHaveBeenCalledWith('/api/audit-scheduler', { signal: undefined });
	});
});
