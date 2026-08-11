import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatBytes(bytes: number): string {
	return domainFormatters.formatBytes(bytes);
}
