import { formatBytes } from '$lib/formatting/main/format-bytes';

export function formatWarehouseBytes(value: number | null): string {
	if (value === null) return '—';
	return value === 0 ? '0 B' : formatBytes(value);
}
