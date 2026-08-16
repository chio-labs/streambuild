// Time-axis arithmetic for the tick timeline: warehouse timestamps are UTC
// millisecond text ("YYYY-MM-DD HH:MM:SS.mmm"), the window is a UTC ms range.

import type { TimelineAxisLabel } from '../types';

const SECOND_MS = 1_000;
const MINUTE_MS = 60 * SECOND_MS;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

// Chosen so a window always renders roughly 3-8 labels.
const STEP_LADDER_MS: readonly number[] = [
	SECOND_MS,
	5 * SECOND_MS,
	15 * SECOND_MS,
	30 * SECOND_MS,
	MINUTE_MS,
	5 * MINUTE_MS,
	15 * MINUTE_MS,
	30 * MINUTE_MS,
	HOUR_MS,
	3 * HOUR_MS,
	6 * HOUR_MS,
	12 * HOUR_MS,
	DAY_MS,
	2 * DAY_MS,
	7 * DAY_MS,
	14 * DAY_MS,
	30 * DAY_MS
];
const MAX_AXIS_LABELS = 8;

export function timestampToMs(value: string): number {
	return Date.parse(`${value.replace(' ', 'T')}Z`);
}

export function msToTimestamp(ms: number): string {
	return new Date(ms).toISOString().replace('T', ' ').slice(0, 23);
}

export function windowFraction(ms: number, startMs: number, endMs: number): number {
	if (endMs <= startMs) return 0;
	return (ms - startMs) / (endMs - startMs);
}

function pad(value: number): string {
	return String(value).padStart(2, '0');
}

function labelText(ms: number, spanMs: number): string {
	const moment: Date = new Date(ms);
	const clock: string = `${pad(moment.getUTCHours())}:${pad(moment.getUTCMinutes())}`;
	const day: string = `${pad(moment.getUTCMonth() + 1)}-${pad(moment.getUTCDate())}`;
	if (spanMs >= 7 * DAY_MS) return day;
	if (spanMs >= DAY_MS) return `${day} ${clock}`;
	if (spanMs < 5 * MINUTE_MS) return `${clock}:${pad(moment.getUTCSeconds())}`;
	return clock;
}

export function axisLabels(startMs: number, endMs: number): TimelineAxisLabel[] {
	const spanMs: number = endMs - startMs;
	if (spanMs <= 0) return [];
	const stepMs: number =
		STEP_LADDER_MS.find((candidate) => spanMs / candidate <= MAX_AXIS_LABELS) ??
		STEP_LADDER_MS[STEP_LADDER_MS.length - 1]!;
	const labels: TimelineAxisLabel[] = [];
	for (let ms = Math.ceil(startMs / stepMs) * stepMs; ms <= endMs; ms += stepMs) {
		labels.push({ fraction: windowFraction(ms, startMs, endMs), text: labelText(ms, spanMs) });
	}
	return labels;
}
