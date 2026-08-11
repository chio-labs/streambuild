<script module lang="ts">
	import type { ModelStatus } from '$lib/domain/types';

	/**
	 * Lineage filter state. Deliberately a small set of *concrete* axes rather
	 * than a query language: StreamBuild has no tags, groups or owners to query
	 * on, so every axis here maps to something the manifest actually carries.
	 *
	 * Empty set = no constraint on that axis (not "match nothing").
	 */
	export type NodeKindFilter = 'source' | 'table' | 'aggregate' | 'view';

	export type GraphFilterState = {
		search: string;
		pipelines: Set<string>;
		kinds: Set<NodeKindFilter>;
		statuses: Set<ModelStatus>;
		anchorsOnly: boolean;
	};

	export function emptyFilters(): GraphFilterState {
		return {
			search: '',
			pipelines: new Set(),
			kinds: new Set(),
			statuses: new Set(),
			anchorsOnly: false
		};
	}

	export function filterCount(filters: GraphFilterState): number {
		return (
			(filters.search.trim() ? 1 : 0) +
			filters.pipelines.size +
			filters.kinds.size +
			filters.statuses.size +
			(filters.anchorsOnly ? 1 : 0)
		);
	}
</script>

<script lang="ts">
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import SearchIcon from '@lucide/svelte/icons/search';
	import XIcon from '@lucide/svelte/icons/x';
	import * as Popover from '$ui-kit/popover/main';
	import type { Project } from '$lib/domain/types';

	type Props = {
		project: Project;
		filters: GraphFilterState;
		matched: number;
		total: number;
		onchange: (next: GraphFilterState) => void;
	};
	let { project, filters, matched, total, onchange }: Props = $props();

	const KIND_LABELS: Record<NodeKindFilter, string> = {
		source: 'Sources',
		table: 'Streaming tables',
		aggregate: 'Aggregates',
		view: 'Terminal views'
	};

	const STATUS_LABELS: Record<ModelStatus, string> = {
		fresh: 'Fresh',
		lagging: 'Lagging',
		stalled: 'Stalled',
		drift: 'Drift',
		source: 'Source'
	};

	const STATUS_ORDER: ModelStatus[] = ['fresh', 'lagging', 'stalled', 'drift'];

	function toggle<T>(set: Set<T>, value: T): Set<T> {
		const next: Set<T> = new Set(set);
		if (next.has(value)) next.delete(value);
		else next.add(value);
		return next;
	}

	const active = $derived(filterCount(filters));
</script>

<div class="flex flex-wrap items-center gap-2">
	<div class="relative w-full sm:w-auto">
		<SearchIcon
			size={12}
			class="text-[var(--sb-text-faint)] pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2"
		/>
		<input
			value={filters.search}
			placeholder="Search name or relation…"
			class="bg-[var(--sb-inset)] w-full rounded-[4px] border border-border py-1.5 pl-7 pr-2.5 font-mono text-[11px] outline-none focus:border-[var(--primary)] sm:w-[210px]"
			oninput={(event) => onchange({ ...filters, search: event.currentTarget.value })}
		/>
	</div>

	<!-- Pipeline is the primary axis: it is one of only two selector forms, and
	     "show me just this pipeline" is the common request. -->
	<Popover.Root>
		<Popover.Trigger
			class="flex items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 font-mono text-[11px] transition-colors {filters
				.pipelines.size
				? 'border-primary text-foreground bg-[var(--sidebar-accent)]'
				: 'text-muted-foreground hover:text-foreground border-border'}"
		>
			Pipelines
			{#if filters.pipelines.size}<span>{filters.pipelines.size}</span>{/if}
			<ChevronDownIcon size={11} />
		</Popover.Trigger>
		<Popover.Content class="w-56 p-2" align="start">
			{#each project.pipelines as pipeline (pipeline.name)}
				<label
					class="hover:bg-[var(--sb-hover)] flex cursor-pointer items-center gap-2.5 rounded-[3px] px-1.5 py-1.5 text-[12px]"
				>
					<input
						type="checkbox"
						class="sb-check"
						checked={filters.pipelines.has(pipeline.name)}
						onchange={() =>
							onchange({ ...filters, pipelines: toggle(filters.pipelines, pipeline.name) })}
					/>
					<span class="truncate font-mono text-[11.5px]">{pipeline.name}</span>
					<span class="text-[var(--sb-text-faint)] ml-auto font-mono text-[10px]"
						>{pipeline.models.length}</span
					>
				</label>
			{/each}
		</Popover.Content>
	</Popover.Root>

	<Popover.Root>
		<Popover.Trigger
			class="flex items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 font-mono text-[11px] transition-colors {filters
				.kinds.size
				? 'border-primary text-foreground bg-[var(--sidebar-accent)]'
				: 'text-muted-foreground hover:text-foreground border-border'}"
		>
			Kind
			{#if filters.kinds.size}<span>{filters.kinds.size}</span>{/if}
			<ChevronDownIcon size={11} />
		</Popover.Trigger>
		<Popover.Content class="w-52 p-2" align="start">
			{#each Object.entries(KIND_LABELS) as [key, label] (key)}
				<label
					class="hover:bg-[var(--sb-hover)] flex cursor-pointer items-center gap-2.5 rounded-[3px] px-1.5 py-1.5 text-[12px]"
				>
					<input
						type="checkbox"
						class="sb-check"
						checked={filters.kinds.has(key as NodeKindFilter)}
						onchange={() =>
							onchange({ ...filters, kinds: toggle(filters.kinds, key as NodeKindFilter) })}
					/>
					{label}
				</label>
			{/each}
		</Popover.Content>
	</Popover.Root>

	<Popover.Root>
		<Popover.Trigger
			class="flex items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 font-mono text-[11px] transition-colors {filters
				.statuses.size || filters.anchorsOnly
				? 'border-primary text-foreground bg-[var(--sidebar-accent)]'
				: 'text-muted-foreground hover:text-foreground border-border'}"
		>
			Status
			{#if filters.statuses.size}<span>{filters.statuses.size}</span>{/if}
			<ChevronDownIcon size={11} />
		</Popover.Trigger>
		<Popover.Content class="w-52 p-2" align="start">
			{#each STATUS_ORDER as status (status)}
				<label
					class="hover:bg-[var(--sb-hover)] flex cursor-pointer items-center gap-2.5 rounded-[3px] px-1.5 py-1.5 text-[12px]"
				>
					<input
						type="checkbox"
						class="sb-check"
						checked={filters.statuses.has(status)}
						onchange={() =>
							onchange({ ...filters, statuses: toggle(filters.statuses, status) })}
					/>
					{STATUS_LABELS[status]}
				</label>
			{/each}
			<div class="my-1 border-t border-border"></div>
			<label
				class="hover:bg-[var(--sb-hover)] flex cursor-pointer items-center gap-2.5 rounded-[3px] px-1.5 py-1.5 text-[12px]"
			>
				<input
					type="checkbox"
					class="sb-check"
					checked={filters.anchorsOnly}
					onchange={() => onchange({ ...filters, anchorsOnly: !filters.anchorsOnly })}
				/>
				Replay anchors only
			</label>
		</Popover.Content>
	</Popover.Root>

	{#if active}
		<button
			class="text-muted-foreground hover:text-foreground flex items-center gap-1 rounded-[4px] border border-border px-2 py-1.5 font-mono text-[11px]"
			onclick={() => onchange(emptyFilters())}
		>
			<XIcon size={11} /> Clear
		</button>
		<span class="text-muted-foreground font-mono text-[11px]">{matched} of {total}</span>
	{/if}
</div>
