import { afterEach, describe, expect, it, vi } from 'vitest';

import { createCopyFeedbackResource } from '$lib/presentation/_resources/copy-feedback.resource';

describe('copy feedback resource', () => {
	afterEach(() => vi.useRealTimers());

	it('given copy feedback when reset is scheduled then it clears after the feedback window', async () => {
		vi.useFakeTimers();
		const reset = vi.fn<() => void>();
		const resource: ReturnType<typeof createCopyFeedbackResource> =
			createCopyFeedbackResource(reset);

		resource.schedule();
		await vi.advanceTimersByTimeAsync(1_199);
		expect(reset).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);

		expect(reset).toHaveBeenCalledTimes(1);
	});
});
