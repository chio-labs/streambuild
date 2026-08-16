import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';

import {
	createWindowFetchDebounce,
	type WindowFetchDebounce
} from '../../../../src/lib/sensor-automation/_resources/window-fetch-debounce.resource';

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

describe('createWindowFetchDebounce', () => {
	it('given rapid schedules when the delay elapses then only the last run fires', () => {
		const debounce: WindowFetchDebounce = createWindowFetchDebounce(300);
		const first: Mock = vi.fn();
		const last: Mock = vi.fn();

		debounce.schedule(first);
		debounce.schedule(last);
		vi.advanceTimersByTime(350);

		expect(first).not.toHaveBeenCalled();
		expect(last).toHaveBeenCalledTimes(1);
	});

	it('given a scheduled run when cancelling then nothing fires', () => {
		const debounce: WindowFetchDebounce = createWindowFetchDebounce(300);
		const run: Mock = vi.fn();

		debounce.schedule(run);
		debounce.cancel();
		vi.advanceTimersByTime(1_000);

		expect(run).not.toHaveBeenCalled();
	});
});
