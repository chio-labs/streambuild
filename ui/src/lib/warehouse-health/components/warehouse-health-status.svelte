<script lang="ts">
	import type { WarehouseHealthStatus } from '$lib/warehouse-health/types';
	import { warehouseHealthTone } from '$lib/warehouse-health/main/warehouse-health-tone';

	type Props = {
		status: WarehouseHealthStatus;
	};

	let { status }: Props = $props();
</script>

<span class="inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.08em]">
	<span class="h-1.5 w-1.5 rounded-full" style:background={warehouseHealthTone(status)}></span>
	<span style:color={warehouseHealthTone(status)}>{status}</span>
</span>
