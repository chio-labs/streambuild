import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatPercent(fraction: number): string {
	return domainFormatters.formatPercent(fraction);
}
