import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatAgo(instant: string | null, reference: string): string {
	return domainFormatters.formatAgo(instant, reference);
}
