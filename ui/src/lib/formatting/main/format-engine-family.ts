import { domainFormatters } from '$lib/formatting/_helpers/format';

export function formatEngineFamily(engine: string | null): string {
	return domainFormatters.formatEngineFamily(engine);
}
