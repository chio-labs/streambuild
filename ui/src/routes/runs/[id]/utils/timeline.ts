import { buildRunTimeline } from '../../../../lib/run-presentation/main/build-run-timeline';
import type { TimelineEvent } from '../../../../lib/run-presentation/types';

export function buildTimeline<T extends TimelineEvent>(
	events: T[],
	running: boolean,
	limit: number = 400
): T[] {
	return buildRunTimeline(events, running, limit);
}
