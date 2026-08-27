import { formatPercent } from '$lib/formatting/main/format-percent';
import type { WarehouseDiskHealth, WarehouseHealth } from '$lib/warehouse-health/types';

function availableFraction(disk: WarehouseDiskHealth): number | null {
	return disk.totalBytes !== null && disk.totalBytes > 0 && disk.unreservedBytes !== null
		? disk.unreservedBytes / disk.totalBytes
		: null;
}

export function warehouseHealthSummary(health: WarehouseHealth): string {
	const disk: WarehouseDiskHealth | undefined =
		health.disks.find((item) => item.status === 'critical') ??
		health.disks.find((item) => item.status === 'warning');
	if (disk) {
		const available: number | null = availableFraction(disk);
		const threshold: number | null =
			disk.status === 'critical'
				? health.capacityCriticalFraction
				: health.capacityWarningFraction;
		const availableText: string = available === null ? 'available capacity unknown' : `${formatPercent(available)} available`;
		const thresholdText: string = threshold === null ? '' : ` · threshold ${formatPercent(threshold)}`;
		return `Storage capacity ${disk.status}: ${disk.name} · ${availableText}${thresholdText}`;
	}
	if (health.inodes.status === 'critical' || health.inodes.status === 'warning') {
		return `Inode capacity ${health.inodes.status}: ${health.inodes.free ?? 'unknown'} free`;
	}
	return health.warnings[0] ?? 'Current point-in-time warehouse diagnostics.';
}
