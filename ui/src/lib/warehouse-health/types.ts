export type WarehouseHealthStatus = 'healthy' | 'warning' | 'critical' | 'unknown';

export type WarehouseDiskHealth = {
	name: string;
	path: string;
	type: string;
	totalBytes: number;
	freeBytes: number;
	unreservedBytes: number;
	keepFreeBytes: number;
	status: WarehouseHealthStatus;
};

export type WarehouseMemoryHealth = {
	residentBytes: number | null;
	hostTotalBytes: number | null;
	cgroupUsedBytes: number | null;
	cgroupLimitBytes: number | null;
	basis: 'cgroup' | 'server_rss_host';
	pressureFraction: number | null;
};

export type WarehouseHealth = {
	availability: 'available' | 'partial' | 'unavailable';
	status: WarehouseHealthStatus;
	adapter: string;
	database: string;
	version: string | null;
	uptimeSeconds: number | null;
	measuredAt: string;
	collectionDurationMs: number;
	stale: boolean;
	warnings: string[];
	disks: WarehouseDiskHealth[];
	inodes: {
		total: number | null;
		free: number | null;
		status: WarehouseHealthStatus;
	};
	memory: WarehouseMemoryHealth | null;
	activity: {
		activeQueries: number;
		activeMerges: number;
		incompleteMutations: number;
	} | null;
	tables: {
		name: string;
		rows: number;
		bytesOnDisk: number;
		activeParts: number;
	}[];
};
