import { afterEach, describe, expect, it, vi } from 'vitest';

import { createTopicPollingResource } from '$lib/topic-browser/_resources/topic-polling.resource';
import type { TopicPollingResource } from '$lib/topic-browser/types';

describe('topic polling resource', () => {
	afterEach(() => vi.useRealTimers());

	it('given brokers remain pending when polling starts then another poll is scheduled', async () => {
		vi.useFakeTimers();
		const poll: ReturnType<typeof vi.fn<() => Promise<boolean>>> = vi
			.fn<() => Promise<boolean>>()
			.mockResolvedValueOnce(true)
			.mockResolvedValue(false);
		const resource: TopicPollingResource = createTopicPollingResource(poll);

		resource.start();
		await vi.advanceTimersByTimeAsync(2_000);
		resource.stop();

		expect(poll).toHaveBeenCalledTimes(2);
	});
});
