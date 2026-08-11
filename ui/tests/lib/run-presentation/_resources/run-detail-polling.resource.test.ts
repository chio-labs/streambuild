import { afterEach, describe, expect, it, vi } from 'vitest';

import { createRunDetailPollingResource } from '$lib/run-presentation/_resources/run-detail-polling.resource';
import type { RunDetailPollingResource } from '$lib/run-presentation/types';

describe('run detail polling resource', () => {
	afterEach((): void => {
		vi.useRealTimers();
	});

	it('given a pending poll when rescheduled then only the latest poll runs', async () => {
		vi.useFakeTimers();
		const poll: ReturnType<typeof vi.fn<() => Promise<void>>> = vi.fn<() => Promise<void>>(
			() => Promise.resolve()
		);
		const resource: RunDetailPollingResource = createRunDetailPollingResource(poll);

		resource.schedule(100);
		resource.schedule(200);
		await vi.advanceTimersByTimeAsync(100);
		expect(poll).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(100);
		resource.stop();

		expect(poll).toHaveBeenCalledTimes(1);
	});
});
