import { describe, expect, it, vi } from 'vitest';

import type { AuditSchedulerPayload } from '$lib/quality-monitoring/types';

const requests: { fetchAuditScheduler: ReturnType<typeof vi.fn> } = vi.hoisted(() => ({
	fetchAuditScheduler: vi.fn()
}));

vi.mock('$lib/quality-monitoring/_api/fetch-audit-scheduler', () => ({
	fetchAuditScheduler: requests.fetchAuditScheduler
}));
vi.mock('$lib/quality-monitoring/_resources/audit-scheduler-polling.resource', () => ({
	createAuditSchedulerPollingResource: vi.fn((refresh: () => Promise<void>) => ({
		start: () => {
			void refresh();
			return vi.fn();
		},
		stop: vi.fn()
	}))
}));

import { createAuditSchedulerState } from '$lib/quality-monitoring/_state/audit-scheduler.state.svelte';
import type { AuditSchedulerState } from '$lib/quality-monitoring/types';

describe('audit scheduler state', () => {
	it('given a scheduler response when state starts then the latest payload is exposed', async () => {
		const payload: AuditSchedulerPayload = {
			enabled: true,
			state: 'idle',
			warehouseNow: null,
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
		requests.fetchAuditScheduler.mockResolvedValueOnce(payload);
		const state: AuditSchedulerState = createAuditSchedulerState();

		state.start();
		await vi.waitFor(() => expect(state.loading).toBe(false));

		expect(state.payload).toEqual(payload);
	});
});
