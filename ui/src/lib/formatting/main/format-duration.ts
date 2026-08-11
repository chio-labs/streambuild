import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatDuration(seconds: number): string {
	return domainFormatters.formatDuration(seconds);
}
