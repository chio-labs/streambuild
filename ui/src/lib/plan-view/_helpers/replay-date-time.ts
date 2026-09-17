import {
	toCalendarDateTime,
	toZoned,
	type CalendarDateTime,
	type ZonedDateTime
} from '@internationalized/date';

function sameWallTime(left: ZonedDateTime, right: ZonedDateTime): boolean {
	return (
		left.year === right.year &&
		left.month === right.month &&
		left.day === right.day &&
		left.hour === right.hour &&
		left.minute === right.minute
	);
}

function occurrencesForLocalTime(
	local: CalendarDateTime,
	timeZone: string
): ZonedDateTime[] {
	const earlier: ZonedDateTime = toZoned(local, timeZone, 'earlier');
	const later: ZonedDateTime = toZoned(local, timeZone, 'later');
	if (earlier.compare(later) === 0 || !sameWallTime(earlier, later)) return [toZoned(local, timeZone)];
	return [earlier, later];
}

export function replayWallTimeOccurrences(
	value: ZonedDateTime,
	timeZone: string
): ZonedDateTime[] {
	return occurrencesForLocalTime(toCalendarDateTime(value), timeZone);
}

export function setReplayWallTime(
	value: ZonedDateTime,
	hour: number,
	minute: number,
	timeZone: string
): ZonedDateTime {
	const local: CalendarDateTime = toCalendarDateTime(value).set({
		hour,
		minute,
		second: 0,
		millisecond: 0
	});
	const occurrences: ZonedDateTime[] = occurrencesForLocalTime(local, timeZone);
	return occurrences.find((occurrence) => occurrence.offset === value.offset) ?? occurrences[0];
}

export function formatUtcOffset(offsetMilliseconds: number): string {
	const totalMinutes: number = Math.round(Math.abs(offsetMilliseconds) / 60_000);
	const hours: number = Math.floor(totalMinutes / 60);
	const minutes: number = totalMinutes % 60;
	const sign: string = offsetMilliseconds >= 0 ? '+' : '−';
	return `UTC${sign}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}
