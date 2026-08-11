import { afterEach, describe, expect, it, vi } from 'vitest';

import { createAuditSchedulerPollingResource } from '$lib/quality-monitoring/_resources/audit-scheduler-polling.resource';
import type { AuditSchedulerPollingResource } from '$lib/quality-monitoring/types';

describe('audit scheduler polling resource', () => {
	afterEach(() => vi.useRealTimers());

	it('given polling starts twice when time advances then only one interval refreshes', async () => {
		vi.useFakeTimers();
		const refresh = vi.fn<() => Promise<void>>(() => Promise.resolve());
		const resource: AuditSchedulerPollingResource = createAuditSchedulerPollingResource(refresh);

		resource.start();
		resource.start();
		await vi.advanceTimersByTimeAsync(10_000);
		resource.stop();

		expect(refresh).toHaveBeenCalledTimes(2);
	});
});
