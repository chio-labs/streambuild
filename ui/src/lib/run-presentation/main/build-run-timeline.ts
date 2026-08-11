import { buildTimeline } from '../_helpers/timeline';
import type { TimelineEvent } from '../types';

export function buildRunTimeline<T extends TimelineEvent>(
	events: T[],
	running: boolean,
	limit: number = 400
): T[] {
	return buildTimeline(events, running, limit);
}
