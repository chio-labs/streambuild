import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatRate(rowsPerSecond: number): string {
	return domainFormatters.formatRate(rowsPerSecond);
}
