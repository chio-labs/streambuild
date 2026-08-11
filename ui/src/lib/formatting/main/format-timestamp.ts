import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatTimestamp(instant: string | null): string {
	return domainFormatters.formatTimestamp(instant);
}
