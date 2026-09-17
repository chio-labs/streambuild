import { parseAbsolute, type ZonedDateTime } from '@internationalized/date';
import { describe, expect, it } from 'vitest';

import {
	formatUtcOffset,
	replayWallTimeOccurrences,
	setReplayWallTime
} from '$lib/plan-view/_helpers/replay-date-time';

describe('replay date and time', () => {
	it('given a repeated wall time when listing occurrences then both offsets remain selectable', () => {
		const firstOccurrence: ZonedDateTime = parseAbsolute(
			'2026-11-01T05:30:00Z',
			'America/New_York'
		);

		const occurrences: ZonedDateTime[] = replayWallTimeOccurrences(
			firstOccurrence,
			'America/New_York'
		);

		expect(occurrences.map((occurrence) => occurrence.toDate().toISOString())).toEqual([
			'2026-11-01T05:30:00.000Z',
			'2026-11-01T06:30:00.000Z'
		]);
		expect(occurrences.map((occurrence) => formatUtcOffset(occurrence.offset))).toEqual([
			'UTC−04:00',
			'UTC−05:00'
		]);
	});

	it('given the later offset when editing into a repeated hour then that offset is preserved', () => {
		const afterTransition: ZonedDateTime = parseAbsolute(
			'2026-11-01T07:00:00Z',
			'America/New_York'
		);

		const edited: ZonedDateTime = setReplayWallTime(
			afterTransition,
			1,
			30,
			'America/New_York'
		);

		expect(edited.toDate().toISOString()).toBe('2026-11-01T06:30:00.000Z');
		expect(formatUtcOffset(edited.offset)).toBe('UTC−05:00');
	});

	it('given an ordinary wall time when listing occurrences then only one instant is returned', () => {
		const ordinary: ZonedDateTime = parseAbsolute(
			'2026-11-02T17:30:00Z',
			'America/New_York'
		);

		expect(replayWallTimeOccurrences(ordinary, 'America/New_York')).toHaveLength(1);
	});

	it('given a skipped wall time when editing then it advances without offering a repeat', () => {
		const beforeTransition: ZonedDateTime = parseAbsolute(
			'2026-03-08T06:30:00Z',
			'America/New_York'
		);

		const edited: ZonedDateTime = setReplayWallTime(
			beforeTransition,
			2,
			30,
			'America/New_York'
		);

		expect(edited.toDate().toISOString()).toBe('2026-03-08T07:30:00.000Z');
		expect(edited.hour).toBe(3);
		expect(replayWallTimeOccurrences(edited, 'America/New_York')).toHaveLength(1);
	});
});
