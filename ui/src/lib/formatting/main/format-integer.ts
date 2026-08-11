import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatInteger(value: number): string {
	return domainFormatters.formatInteger(value);
}
