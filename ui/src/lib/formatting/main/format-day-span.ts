import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatDaySpan(days: number): string {
	return domainFormatters.formatDaySpan(days);
}
