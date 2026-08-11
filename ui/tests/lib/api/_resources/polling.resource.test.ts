import { afterEach, describe, expect, it, vi } from 'vitest';

import { createPollingResource } from '$lib/api/_resources/polling.resource';

describe('polling resource', () => {
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('given a visible document when polling starts twice then only one refresh interval runs', async () => {
		vi.useFakeTimers();
		vi.stubGlobal('document', { hidden: false });
		const refresh = vi.fn<() => Promise<void>>(() => Promise.resolve());
		const resource: ReturnType<typeof createPollingResource> = createPollingResource(refresh);

		resource.start();
		resource.start();
		await vi.advanceTimersByTimeAsync(30_000);
		resource.stop();
		await vi.advanceTimersByTimeAsync(30_000);

		expect(refresh).toHaveBeenCalledTimes(1);
	});
});
