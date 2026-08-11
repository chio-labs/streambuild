import type { Plan } from '$lib/planning/types';

export function planBoundaryColumns(root: Plan['replayRoots'][number]): string | null {
	const columns: Plan['replayRoots'][number]['replayColumns'] = root.replayColumns;
	if (root.boundaryMode === 'offsets') {
		const pair: string = [columns.partition, columns.offset].filter(Boolean).join(' / ');
		return pair || null;
	}
	if (root.boundaryMode === 'timestamp' || root.boundaryMode === 'cursor') {
		return columns.timestamp ?? null;
	}
	return columns.landed_at ?? null;
}
