import { afterEach, describe, expect, it, vi } from 'vitest';

import { createCopyFeedbackResource } from '$lib/message-browser/_resources/copy-feedback.resource';
import type { CopyFeedbackResource } from '$lib/message-browser/types';

describe('message copy feedback resource', () => {
	afterEach(() => vi.useRealTimers());

	it('given feedback is rescheduled when the timeout expires then reset runs once', async () => {
		vi.useFakeTimers();
		const reset: () => void = vi.fn();
		const resource: CopyFeedbackResource = createCopyFeedbackResource(reset);

		resource.schedule();
		resource.schedule();
		await vi.advanceTimersByTimeAsync(1_200);

		expect(reset).toHaveBeenCalledTimes(1);
	});
});
