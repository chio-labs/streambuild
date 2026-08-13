import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';

import { createSensorsPollingResource } from '../../../../src/routes/sensors/_resources/sensors-polling.resource';
import type { SensorsPollingResource } from '../../../../src/routes/sensors/types';

describe('sensors polling resource', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('given a started resource when the interval elapses then refresh repeats until stopped', () => {
		const refresh: Mock<() => Promise<void>> = vi.fn(() => Promise.resolve());
		const resource: SensorsPollingResource = createSensorsPollingResource(refresh);

		const stop: () => void = resource.start();
		vi.advanceTimersByTime(10_000);
		stop();
		vi.advanceTimersByTime(30_000);

		expect(refresh).toHaveBeenCalledTimes(2);
	});
});
