import type { Selector } from '$lib/planning/types';

export function parseSelector(token: string): Selector | null {
	const trimmed: string = token.trim();
	if (!trimmed) return null;
	if (trimmed.startsWith('pipeline:')) {
		const name: string = trimmed.slice('pipeline:'.length);
		return name ? { kind: 'pipeline', name } : null;
	}
	if (trimmed.startsWith('model:')) {
		const name: string = trimmed.slice('model:'.length);
		return name ? { kind: 'model', name } : null;
	}
	return { kind: 'model', name: trimmed };
}
