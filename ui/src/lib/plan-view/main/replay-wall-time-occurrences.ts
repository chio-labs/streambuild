import type { ZonedDateTime } from '@internationalized/date';
import { replayWallTimeOccurrences as occurrences } from '$lib/plan-view/_helpers/replay-date-time';

export function replayWallTimeOccurrences(
	value: ZonedDateTime,
	timeZone: string
): ZonedDateTime[] {
	return occurrences(value, timeZone);
}
