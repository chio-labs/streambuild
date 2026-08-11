<script lang="ts">
	import SlidersIcon from '@lucide/svelte/icons/sliders-horizontal';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import * as Popover from '$ui-kit/popover/main';
	import { NODE_FIELD_LABELS } from '$lib/lineage/constants';
	import { getNodeFields } from '$lib/lineage/main/get-node-fields';
	import type { NodeFieldSet } from '$lib/lineage/types';

	const nodeFields = getNodeFields();
	const keys: (keyof NodeFieldSet)[] = Object.keys(NODE_FIELD_LABELS) as (keyof NodeFieldSet)[];
	const activeCount = $derived(Object.values(nodeFields.value).filter(Boolean).length);
</script>

<Popover.Root>
	<Popover.Trigger
		class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] flex items-center gap-1.5 rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11px]"
	>
		<SlidersIcon size={12} /> Node fields
		<span class="text-[var(--sb-text-faint)]">{activeCount}</span>
		<ChevronDownIcon size={12} />
	</Popover.Trigger>
	<Popover.Content class="w-56 p-2" align="start">
		<div
			class="text-[var(--sb-text-faint)] px-1 pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
		>
			Show on nodes
		</div>
		{#each keys as key (key)}
			<label
				class="hover:bg-[var(--sb-hover)] flex cursor-pointer items-center gap-2.5 rounded-[3px] px-1.5 py-1.5 text-[12px]"
			>
				<input
					type="checkbox"
					class="sb-check"
					checked={nodeFields.value[key]}
					onchange={() => nodeFields.toggle(key)}
				/>
				{NODE_FIELD_LABELS[key]}
			</label>
		{/each}
		<button
			class="text-muted-foreground hover:text-foreground mt-1 w-full rounded-[3px] border border-border px-2 py-1.5 font-mono text-[10.5px]"
			onclick={() => nodeFields.reset()}
		>
			Reset
		</button>
	</Popover.Content>
</Popover.Root>
