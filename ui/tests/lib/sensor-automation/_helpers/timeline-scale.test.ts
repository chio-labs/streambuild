import { describe, expect, it } from 'vitest';

import {
	axisLabels,
	msToTimestamp,
	timestampToMs,
	windowFraction
} from '../../../../src/lib/sensor-automation/_helpers/timeline-scale';
import type { TimelineAxisLabel } from '../../../../src/lib/sensor-automation/types';

describe('timeline scale', () => {
	it('given a warehouse timestamp when converting to ms and back then the text round-trips', () => {
		const text = '2026-08-13 07:55:09.123';
		expect(msToTimestamp(timestampToMs(text))).toBe(text);
	});

	it('given a window when positioning instants then fractions reflect their place', () => {
		expect(windowFraction(1_500, 1_000, 2_000)).toBe(0.5);
		expect(windowFraction(1_000, 1_000, 2_000)).toBe(0);
		expect(windowFraction(3_000, 1_000, 2_000)).toBe(2);
		expect(windowFraction(1_000, 1_000, 1_000)).toBe(0);
	});

	it('given an hour window when building axis labels then labels stay bounded and inside', () => {
		const hourStart: number = timestampToMs('2026-08-13 06:00:00.000');
		const labels: TimelineAxisLabel[] = axisLabels(hourStart, hourStart + 60 * 60 * 1_000);
		expect(labels.length).toBeGreaterThanOrEqual(3);
		expect(labels.length).toBeLessThanOrEqual(9);
		for (const label of labels) {
			expect(label.fraction).toBeGreaterThanOrEqual(0);
			expect(label.fraction).toBeLessThanOrEqual(1);
		}
		expect(labels[0]?.text).toBe('06:00');
	});

	it('given a two-week window when building axis labels then labels use day text', () => {
		const start: number = timestampToMs('2026-08-01 00:00:00.000');
		const labels: TimelineAxisLabel[] = axisLabels(start, start + 14 * 24 * 60 * 60 * 1_000);
		expect(labels[0]?.text).toBe('08-01');
	});

	it('given an inverted window when building axis labels then no labels return', () => {
		expect(axisLabels(2_000, 1_000)).toEqual([]);
	});
});
