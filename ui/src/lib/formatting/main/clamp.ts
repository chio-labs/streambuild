import { domainFormatters } from '$lib/formatting/_helpers/format';

export function clamp(value: number, min: number, max: number): number {
	return domainFormatters.clamp(value, min, max);
}
