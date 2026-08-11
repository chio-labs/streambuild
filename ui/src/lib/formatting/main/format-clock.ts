import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatClock(instant: string | null): string {
	return domainFormatters.formatClock(instant);
}
