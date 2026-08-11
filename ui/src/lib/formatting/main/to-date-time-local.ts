import { domainFormatters } from '$lib/formatting/_helpers/format';

export function toDateTimeLocal(instant: string): string {
	return domainFormatters.toDateTimeLocal(instant);
}
