import { domainFormatters } from '$lib/formatting/_helpers/format';

export function fromDateTimeLocal(value: string): string {
	return domainFormatters.fromDateTimeLocal(value);
}
