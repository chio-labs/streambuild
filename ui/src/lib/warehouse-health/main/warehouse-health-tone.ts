import type { WarehouseHealthStatus } from '$lib/warehouse-health/types';

export function warehouseHealthTone(status: WarehouseHealthStatus): string {
	if (status === 'healthy') return 'var(--sb-success)';
	if (status === 'warning') return 'var(--sb-warning)';
	if (status === 'critical') return 'var(--sb-error)';
	return 'var(--sb-text-faint)';
}
