import { domainFormatters } from '$lib/formatting/_helpers/format';

export function daysBetween(from: string, to: string): number {
	return domainFormatters.daysBetween(from, to);
}
