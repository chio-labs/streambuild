<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import MaximizeIcon from '@lucide/svelte/icons/maximize';
	import PlayIcon from '@lucide/svelte/icons/play';
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import { getApp } from '$lib/api/main/project/get-app';
	import NodeFieldsPopover from '$lib/presentation/components/lineage/node-fields-popover.svelte';
	import GraphFilters from '$lib/presentation/components/lineage/graph-filters.svelte';
	import GraphInspector from '$lib/presentation/components/graph/graph-inspector.svelte';
	import LineageCanvas from '$lib/presentation/components/lineage/lineage-canvas.svelte';
	import EdgeLegend from '$lib/presentation/components/lineage/edge-legend.svelte';
	import RunPanel from '$lib/presentation/components/run-panel.svelte';
	import { getProject } from '$lib/api/main/project/get-project';
	import { DEFAULT_FIT, type FitOptions } from '$lib/presentation/components/lineage/flow-controller.svelte';
	import { createLineageView } from '$lib/lineage-view/main/create-lineage-view';
	import type { LineageViewTypes } from '$lib/lineage-view/types';

	const project = getProject();
	const app = getApp();
	const lineageView = createLineageView();
	const snapshot = $derived(lineageView.snapshot(page.url, project, app.deployments));
	const mode = $derived(snapshot.mode);
	const groupMode = $derived(snapshot.groupMode);
	const filters = $derived(snapshot.filters);
	const showDeployments = $derived(snapshot.showDeployments);
	const fullGraph = $derived(snapshot.fullGraph);
	const graph = $derived(snapshot.graph);
	const counts = $derived(snapshot.counts);
	let inspectorWidth = $state<number>(460);

	function setFilters(next: LineageViewTypes['filters']): void {
		void goto(lineageView.filtersUrl(page.url, next), {
			replaceState: true,
			noScroll: true,
			keepFocus: true
		});
	}

	function setShowDeployments(next: boolean): void {
		void goto(lineageView.deploymentsUrl(page.url, next), {
			replaceState: true,
			noScroll: true,
			keepFocus: true
		});
	}

	let selectedId = $state<string | null>(null);
	let selectedIds = $state<Set<string>>(new Set());
	let fitView = $state<((options?: FitOptions) => void) | undefined>();
	let runOpen = $state<boolean>(false);

	const runSelection = $derived.by((): string[] => {
		return [
			...new Set(
				graph.nodes
					.filter((node) => selectedIds.has(node.id) && node.logicalType !== 'source')
					.map((node) => node.logicalName)
			)
		];
	});
	let cyclicPairs = $state<[string, string][]>([]);
	let canvas = $state<{ relayout: () => void; clearSelection: () => void } | undefined>();

	const selectedNode = $derived<LineageViewTypes['node'] | null>(
		selectedId ? (graph.nodes.find((node) => node.id === selectedId) ?? null) : null
	);

	function resetLayout(): void {
		canvas?.relayout();
		inspectorWidth = 460;
		queueMicrotask(() => fitView?.(DEFAULT_FIT));
	}

	function setGroupMode(next: 'none' | 'boxes' | 'lanes'): void {
		void goto(lineageView.groupUrl(page.url, next), {
			replaceState: true,
			noScroll: true,
			keepFocus: true
		});
	}

	function setMode(next: LineageViewTypes['mode']): void {
		void goto(lineageView.modeUrl(page.url, next), {
			replaceState: true,
			noScroll: true,
			keepFocus: true
		});
	}

	let resizing = $state<boolean>(false);

	function startResize(event: PointerEvent): void {
		resizing = true;
		(event.target as HTMLElement).setPointerCapture(event.pointerId);
	}

	function onResize(event: PointerEvent): void {
		if (!resizing) return;
		const next: number = window.innerWidth - event.clientX;
		inspectorWidth = Math.min(Math.max(next, 320), 720);
	}

	function endResize(): void {
		resizing = false;
	}
</script>

<AppTopbar title="Lineage" />

<div class="flex min-h-0 flex-1 flex-col">
	<!-- toolbar -->
	<div class="flex shrink-0 flex-wrap items-center gap-2.5 border-b border-border px-3 py-2.5 sm:px-[18px]">
		<!-- The flagship control. Logical is the authored graph; Physical is what
		     actually exists in ClickHouse and is what you debug. -->
		<div class="flex overflow-hidden rounded-[4px] border border-border">
			<button
				class="px-3 py-1.5 font-mono text-[11px] transition-colors {mode === 'logical'
					? 'bg-[var(--sb-hover)] text-foreground'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => setMode('logical')}
			>
				Logical
			</button>
			<button
				class="border-l border-border px-3 py-1.5 font-mono text-[11px] transition-colors {mode ===
				'physical'
					? 'bg-[var(--sb-hover)] text-foreground'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => setMode('physical')}
			>
				Physical
			</button>
		</div>

		{#if mode === 'physical' && app.deployments.length > 0}
			<button
				class="rounded-[4px] border border-border px-3 py-1.5 font-mono text-[11px] transition-colors {showDeployments
					? 'bg-[var(--sb-hover)] text-foreground'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => setShowDeployments(!showDeployments)}
				title="Show deployment-suffixed relations, including orphans nothing points at"
			>
				Deployments
			</button>
		{/if}

		<span class="text-[var(--sb-text-faint)] hidden max-w-[380px] font-mono text-[10.5px] leading-snug xl:inline">
			{#if mode === 'logical'}
				authored sources, models and typed reference edges
			{:else}
				every ClickHouse object: kafka__ → mv__ → raw__ → mv__model → tbl__model
			{/if}
		</span>

		<div class="flex w-full flex-wrap items-center gap-2.5 sm:w-auto xl:ml-auto">
			<div class="hidden xl:block"><EdgeLegend /></div>
			<div class="flex overflow-hidden rounded-[4px] border border-border">
				{#each [['none', 'Flat'], ['boxes', 'Boxes'], ['lanes', 'Lanes']] as [value, label] (value)}
					<button
						class="border-l border-border px-2.5 py-1.5 font-mono text-[11px] transition-colors first:border-l-0 {groupMode ===
						value
							? 'bg-[var(--sb-hover)] text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
						onclick={() => setGroupMode(value as 'none' | 'boxes' | 'lanes')}
					>
						{label}
					</button>
				{/each}
			</div>
			<NodeFieldsPopover />
			<button
				class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] flex items-center gap-1.5 rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11px]"
				onclick={resetLayout}
			>
				<RotateIcon size={12} /> Reset layout
			</button>
			<button
				class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] grid h-[30px] w-[30px] place-items-center rounded-[4px] border border-border"
				aria-label="Fit view"
				onclick={() => fitView?.(DEFAULT_FIT)}
			>
				<MaximizeIcon size={13} />
			</button>
			<button
				class="bg-primary flex items-center gap-1.5 rounded-[4px] px-3 py-1.5 font-mono text-[11px] font-medium text-white"
				onclick={() => (runOpen = true)}
			>
				<PlayIcon size={12} /> Execute
			</button>
		</div>
	</div>

	<!-- filters -->
	<div class="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2 sm:px-[18px]">
		<GraphFilters
			{project}
			{filters}
			matched={graph.nodes.length}
			total={fullGraph.nodes.length}
			onchange={setFilters}
		/>
	</div>

	<!-- status strip -->
	<div
		class="text-muted-foreground flex shrink-0 items-center gap-4 overflow-x-auto whitespace-nowrap border-b border-border px-3 py-1.5 font-mono text-[10.5px] sm:px-[18px]"
	>
		<span>{graph.nodes.length} nodes · {graph.edges.length} edges</span>
		<span class="flex items-center gap-1.5"
			><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-success)]"></span>{counts.fresh} fresh</span
		>
		{#if counts.lagging}
			<span class="flex items-center gap-1.5"
				><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-warning)]"></span>{counts.lagging}
				lagging</span
			>
		{/if}
		{#if counts.stalled}
			<span class="flex items-center gap-1.5"
				><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-error)]"></span>{counts.stalled}
				stalled</span
			>
		{/if}
		{#if cyclicPairs.length}
			<span class="ml-auto" style:color="var(--sb-warning)">
				{cyclicPairs.map(([a, b]) => `${a} and ${b}`).join(', ')} reference each other — box order is
				approximate
			</span>
		{/if}
		{#if counts.drift}
			<span class="flex items-center gap-1.5"
				><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-stale)]"></span>{counts.drift} drift</span
			>
		{/if}
		{#if counts.unknown}
			<span class="flex items-center gap-1.5"
				><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-text-faint)]"></span>{counts.unknown}
				unknown</span
			>
		{/if}
	</div>

	<div class="flex min-h-0 flex-1 flex-col overflow-y-auto md:flex-row md:overflow-hidden">
		<!-- canvas -->
		<div class="min-h-[360px] min-w-0 flex-1">
			{#key mode}
				<LineageCanvas
					bind:this={canvas}
					{project}
					{graph}
					{groupMode}
					compactNodes={mode === 'physical'}
					collapseGroupsByDefault={mode === 'physical'}
					layoutSalt={mode}
					bind:selectedId
					bind:selectedIds
					bind:fitView
					onCycles={(pairs) => (cyclicPairs = pairs)}
				/>
			{/key}
		</div>

		{#if selectedNode}
			<!-- drag handle -->
			<div
				class="hover:bg-primary hidden w-[3px] shrink-0 cursor-col-resize bg-[var(--border-subtle)] transition-colors md:block"
				role="separator"
				aria-orientation="vertical"
				onpointerdown={startResize}
				onpointermove={onResize}
				onpointerup={endResize}
			></div>
			<div
				class="lineage-inspector max-h-[45vh] w-full shrink-0 overflow-y-auto border-t border-border md:max-h-none md:border-l md:border-t-0"
				style="--inspector-width: {inspectorWidth}px"
			>
				<GraphInspector
					node={selectedNode}
					{mode}
					onclose={() => canvas?.clearSelection()}
				/>
			</div>
		{/if}
	</div>
</div>

<RunPanel bind:open={runOpen} selection={runSelection} />

<style>
	@media (min-width: 768px) {
		.lineage-inspector {
			width: var(--inspector-width);
		}
	}
</style>
