import { domainFormatters } from '$lib/formatting/_helpers/format';

export function secondsBetween(from: string, to: string): number {
	return domainFormatters.secondsBetween(from, to);
}
