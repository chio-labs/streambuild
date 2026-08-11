import { domainFormatters } from '$lib/formatting/_helpers/format';

export function parseUtc(instant: string): Date {
	return domainFormatters.parseUtc(instant);
}
