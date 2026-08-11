import { afterEach, describe, expect, it, vi } from 'vitest';

import { createKafkaLagRetryResource } from '$lib/api/_resources/kafka-lag-retry.resource';
import type { Project } from '$lib/domain/types';

describe('Kafka lag retry resource', () => {
	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('given unresolved Kafka lag when a retry is scheduled then refresh runs after the first delay', async () => {
		vi.useFakeTimers();
		vi.stubGlobal('document', { hidden: false });
		const refresh = vi.fn<() => Promise<void>>(() => Promise.resolve());
		const project: Project = {
			sources: [{ kind: 'kafka', live: { kafkaLagMessages: null } }]
		} as unknown as Project;
		const resource: ReturnType<typeof createKafkaLagRetryResource> =
			createKafkaLagRetryResource(refresh);

		resource.schedule(project);
		resource.schedule(project);
		await vi.advanceTimersByTimeAsync(1_000);

		expect(refresh).toHaveBeenCalledTimes(1);
	});
});
