<script module lang="ts">
	import type { ModelStatus } from '$lib/domain/types';

	export type CollapsedGroupData = {
		groupKey: string;
		label: string;
		sublabel: string | null;
		modelCount: number;
		countLabel?: 'models' | 'objects';
		groupKind?: 'pipeline' | 'shared sources' | 'ungrouped';
		statusCounts: Record<ModelStatus, number>;
		ontoggle: (groupKey: string) => void;
	};
</script>

<script lang="ts">
	import { Handle, Position, type NodeProps } from '@xyflow/svelte';
	import WorkflowIcon from '@lucide/svelte/icons/workflow';
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';

	let { data, selected }: NodeProps = $props();
	const group = $derived(data as unknown as CollapsedGroupData);

	const bars = $derived(
		(['fresh', 'lagging', 'stalled', 'drift', 'unknown'] as ModelStatus[])
			.map((status) => ({ status, count: group.statusCounts[status] ?? 0 }))
			.filter((entry) => entry.count > 0)
	);

	const colour: Record<string, string> = {
		fresh: 'var(--sb-success)',
		lagging: 'var(--sb-warning)',
		stalled: 'var(--sb-error)',
		drift: 'var(--sb-stale)',
		unknown: 'var(--sb-text-faint)'
	};
</script>

<!-- A whole pipeline as one node. This is what makes 20+ pipelines navigable. -->
<div class="w-[236px]">
	<!-- stacked-card affordance -->
	<div
		class="mx-auto h-0 w-[88%] rounded-[2px] border-t-2"
		style:border-color="var(--sb-group-border)"
	></div>
	<div
		class="mx-auto mt-[3px] h-0 w-[94%] rounded-[2px] border-t-2"
		style:border-color="var(--sb-group-border)"
	></div>
<div
	class="bg-card relative mt-[3px] w-full overflow-hidden rounded-[7px] border-2 px-3 py-2.5"
	style:border-color={selected ? 'var(--primary)' : 'var(--sb-group-border-strong)'}
	style:box-shadow="var(--sb-node-shadow)"
>
	<Handle type="target" position={Position.Left} class="!border-border !bg-muted !h-2 !w-2" />

	<div class="flex items-center gap-2">
		<span
			class="grid h-7 w-7 shrink-0 place-items-center rounded-md"
			style:background="var(--sb-group-fill-strong)"
			style:color="var(--muted-foreground)"
		>
			<WorkflowIcon size={15} />
		</span>
		<div class="min-w-0 flex-1">
			<div class="truncate font-mono text-[12px] font-medium leading-tight" title={group.label}>
				{group.label}
			</div>
			<div class="text-[var(--sb-text-faint)] mt-[3px] font-mono text-[9.5px] uppercase tracking-[0.1em]">
				{group.groupKind ?? 'pipeline'} · {group.modelCount} {group.countLabel ?? 'models'}
			</div>
		</div>
		<button
			class="text-muted-foreground hover:text-foreground grid h-[20px] w-[20px] shrink-0 place-items-center rounded-[3px]"
			aria-label="Expand {group.groupKind ?? 'pipeline'}"
			onclick={(event) => {
				event.stopPropagation();
				group.ontoggle(group.groupKey);
			}}
		>
			<ChevronRightIcon size={13} />
		</button>
	</div>

	{#if bars.length}
		<div class="mt-2 flex h-[5px] gap-[2px] overflow-hidden rounded-[2px]">
			{#each bars as bar (bar.status)}
				<span
					style:flex={bar.count}
					style:background={colour[bar.status]}
					title="{bar.count} {bar.status}"
				></span>
			{/each}
		</div>
	{/if}

	<Handle type="source" position={Position.Right} class="!border-border !bg-muted !h-2 !w-2" />
</div>
</div>
