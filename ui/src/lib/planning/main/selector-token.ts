import type { Selector } from '$lib/planning/types';

export function selectorToken(selector: Selector): string {
	return selector.kind === 'pipeline' ? `pipeline:${selector.name}` : selector.name;
}
