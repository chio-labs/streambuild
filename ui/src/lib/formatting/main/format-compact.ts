import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatCompact(value: number): string {
	return domainFormatters.formatCompact(value);
}
