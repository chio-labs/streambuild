import { formatUtcOffset as formatOffset } from '$lib/plan-view/_helpers/replay-date-time';

export function formatUtcOffset(offsetMilliseconds: number): string {
	return formatOffset(offsetMilliseconds);
}
