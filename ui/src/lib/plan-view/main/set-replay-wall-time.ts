import type { ZonedDateTime } from '@internationalized/date';
import { setReplayWallTime as setWallTime } from '$lib/plan-view/_helpers/replay-date-time';

export function setReplayWallTime(
	value: ZonedDateTime,
	hour: number,
	minute: number,
	timeZone: string
): ZonedDateTime {
	return setWallTime(value, hour, minute, timeZone);
}
