import { domainFormatters } from '$lib/formatting/_helpers/format';

export function configureTimeZone(timeZone: string): void {
	domainFormatters.configureTimeZone(timeZone);
}
