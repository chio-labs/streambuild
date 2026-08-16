import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SensorTick, TickTimelineState } from '../../../../src/lib/sensor-automation/types';

const requests = vi.hoisted(() => ({
	fetchSensorTicks: vi.fn()
}));

vi.mock('../../../../src/lib/sensor-automation/_api/sensor-collection', () => ({
	fetchSensors: vi.fn(),
	fetchSensorTicks: requests.fetchSensorTicks
}));

import { createTickTimeline } from '../../../../src/lib/sensor-automation/main/_create-tick-timeline.svelte';

const NOW_MS: number = Date.parse('2026-08-13T12:00:00.000Z');

function tick(startedAt: string): SensorTick {
	return {
		tickId: `tick-${startedAt}`,
		sensorName: 'quality_alerts',
		definitionFingerprint: 'abc',
		kind: 'event',
		eventId: 'event-1',
		eventKind: 'AuditCompleted',
		attempt: 1,
		status: 'failed',
		startedAt,
		completedAt: null,
		errorMessage: 'boom',
		skipReason: null,
		cursor: null
	};
}

beforeEach(() => {
	vi.useFakeTimers();
	vi.setSystemTime(NOW_MS);
	requests.fetchSensorTicks.mockResolvedValue({ sensorName: 'quality_alerts', ticks: [] });
});

afterEach(() => {
	vi.useRealTimers();
	requests.fetchSensorTicks.mockReset();
});

describe('createTickTimeline', () => {
	it('given seed ticks when initializing then the default window wraps them without fetching', () => {
		const timeline: TickTimelineState = createTickTimeline(() => 'quality_alerts');

		timeline.initialize([tick('2026-08-13 11:00:00.000')]);

		expect(timeline.ready).toBe(true);
		expect(timeline.endMs).toBe(NOW_MS);
		expect(timeline.startMs).toBeLessThan(Date.parse('2026-08-13T11:00:00.000Z'));
		expect(requests.fetchSensorTicks).not.toHaveBeenCalled();
	});

	it('given a zoom gesture when the debounce settles then the anchored window is refetched', async () => {
		const timeline: TickTimelineState = createTickTimeline(() => 'quality_alerts');
		timeline.initialize([tick('2026-08-13 11:00:00.000')]);
		const spanBefore: number = timeline.endMs - timeline.startMs;

		timeline.zoomAt(0.5, -400);
		expect(timeline.loading).toBe(true);
		await vi.advanceTimersByTimeAsync(350);

		expect(timeline.endMs - timeline.startMs).toBeLessThan(spanBefore);
		expect(requests.fetchSensorTicks).toHaveBeenCalledTimes(1);
		const window: { after: string; before: string; limit: number } =
			requests.fetchSensorTicks.mock.calls[0]?.[2];
		expect(window.limit).toBe(500);
		expect(Date.parse(`${window.after.replace(' ', 'T')}Z`)).toBe(timeline.startMs);
		expect(Date.parse(`${window.before.replace(' ', 'T')}Z`)).toBe(timeline.endMs);
	});

	it('given repeated pans when the debounce settles then the window clamps to now and fetches once', async () => {
		const timeline: TickTimelineState = createTickTimeline(() => 'quality_alerts');
		timeline.initialize([tick('2026-08-13 11:00:00.000')]);

		timeline.panBy(0.5);
		timeline.panBy(0.5);
		timeline.panBy(0.5);
		await vi.advanceTimersByTimeAsync(350);

		expect(timeline.endMs).toBe(NOW_MS);
		expect(requests.fetchSensorTicks).toHaveBeenCalledTimes(1);
	});

	it('given a zoomed window when resetting then the seeded window returns', async () => {
		const timeline: TickTimelineState = createTickTimeline(() => 'quality_alerts');
		timeline.initialize([tick('2026-08-13 11:00:00.000')]);
		const defaultStart: number = timeline.startMs;

		timeline.zoomAt(0.2, -600);
		timeline.reset();
		await vi.advanceTimersByTimeAsync(350);

		expect(timeline.startMs).toBe(defaultStart);
		expect(timeline.endMs).toBe(NOW_MS);
	});

	it('given a pending fetch when stopping then no request is issued', async () => {
		const timeline: TickTimelineState = createTickTimeline(() => 'quality_alerts');
		timeline.initialize([tick('2026-08-13 11:00:00.000')]);

		timeline.zoomAt(0.5, -200);
		timeline.stop();
		await vi.advanceTimersByTimeAsync(1_000);

		expect(requests.fetchSensorTicks).not.toHaveBeenCalled();
	});
});
