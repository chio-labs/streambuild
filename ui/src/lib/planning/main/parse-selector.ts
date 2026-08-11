import type { Selector } from '$lib/planning/types';

export function parseSelector(token: string): Selector | null {
	const trimmed: string = token.trim();
	if (!trimmed) return null;
	if (trimmed.startsWith('pipeline:')) {
		const name: string = trimmed.slice('pipeline:'.length);
		return name ? { kind: 'pipeline', name } : null;
	}
	return { kind: 'model', name: trimmed };
}
