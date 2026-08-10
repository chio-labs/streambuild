<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import MaximizeIcon from '@lucide/svelte/icons/maximize';
	import PlayIcon from '@lucide/svelte/icons/play';
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import { app } from '$lib/api/store.svelte';
	import NodeFieldsPopover from '$lib/components/lineage/node-fields-popover.svelte';
	import GraphFilters, { emptyFilters, filterCount } from '$lib/components/lineage/graph-filters.svelte';
	import type { GraphFilterState, NodeKindFilter } from '$lib/components/lineage/graph-filters.svelte';
	import GraphInspector from '$lib/components/graph/graph-inspector.svelte';
	import LineageCanvas from '$lib/components/lineage/lineage-canvas.svelte';
	import EdgeLegend from '$lib/components/lineage/edge-legend.svelte';
	import RunPanel from '$lib/components/run-panel.svelte';
	import { getProject } from '$lib/api';
	import { buildLogicalGraph, buildPhysicalGraph, modelByName } from '$lib/domain/derive';
	import { DEFAULT_FIT, type FitOptions } from '$lib/lineage/flow-controller.svelte';
	import { nodeFields } from '$lib/lineage/node-fields.svelte';
	import type { Graph, GraphMode, GraphNode, ModelStatus, Project } from '$lib/domain/types';

	const project: Project = getProject();

	// Mode lives in the URL so a physical view is shareable — same principle as
	// selection on the Plan page: every surface is just a link constructor.
	const mode = $derived<GraphMode>(
		page.url.searchParams.get('mode') === 'physical' ? 'physical' : 'logical'
	);
	let inspectorWidth = $state<number>(460);

	// Filters live in the URL, so a filtered lineage view is shareable and other
	// pages can deep-link into one (e.g. /lineage?pipeline=order_events).
	//
	// The URL is the ONLY source of truth — same lesson as the Plan page. A local
	// mirror synced back by a guarded $effect cannot work: `replaceState` from
	// $app/navigation is shallow routing and never updates `page.url`, so the
	// guard always compared against a stale search string and reset the filters
	// right after every change. Deriving from `page.url` and navigating with
	// `goto` removes the mirror, the guard, and the race together.
	const filters = $derived.by((): GraphFilterState => {
		const params = page.url.searchParams;
		return {
			search: params.get('q') ?? '',
			pipelines: new Set(params.getAll('pipeline')),
			kinds: new Set(params.getAll('kind') as NodeKindFilter[]),
			statuses: new Set(params.getAll('status') as ModelStatus[]),
			anchorsOnly: params.get('anchors') === '1'
		};
	});

	function setFilters(next: GraphFilterState): void {
		const url = new URL(page.url);
		for (const key of ['q', 'pipeline', 'kind', 'status', 'anchors']) url.searchParams.delete(key);
		if (next.search.trim()) url.searchParams.set('q', next.search.trim());
		for (const value of next.pipelines) url.searchParams.append('pipeline', value);
		for (const value of next.kinds) url.searchParams.append('kind', value);
		for (const value of next.statuses) url.searchParams.append('status', value);
		if (next.anchorsOnly) url.searchParams.set('anchors', '1');
		void goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	}

	// Deployment relations are off by default: on a busy target they multiply
	// every model by its retained deployments, which buries the shape of the
	// graph. Turned on, they are the only view that shows what is orphaned.
	const showDeployments = $derived(page.url.searchParams.get('deployments') === '1');

	function setShowDeployments(next: boolean): void {
		const url = new URL(page.url);
		if (next) url.searchParams.set('deployments', '1');
		else url.searchParams.delete('deployments');
		void goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	}

	const fullGraph = $derived<Graph>(
		mode === 'logical'
			? buildLogicalGraph(project)
			: buildPhysicalGraph(project, showDeployments ? app.deployments : [])
	);

	function nodeKind(node: Graph['nodes'][number]): NodeKindFilter {
		if (node.logicalType === 'source') return 'source';
		if (node.logicalType === 'view') return 'view';
		return modelByName(project, node.logicalName)?.isAggregate ? 'aggregate' : 'table';
	}

	function matches(node: Graph['nodes'][number]): boolean {
		const needle: string = filters.search.trim().toLowerCase();
		if (
			needle &&
			!`${node.label} ${node.logicalName} ${node.sublabel ?? ''}`.toLowerCase().includes(needle)
		) {
			return false;
		}
		if (filters.pipelines.size) {
			const pipeline: string | undefined = modelByName(project, node.logicalName)?.pipeline;
			// Sources have no pipeline of their own — keep one that feeds a selected
			// pipeline, otherwise the subgraph would start mid-air.
			const feedsSelected: boolean =
				node.logicalType === 'source' &&
				project.pipelines.some(
					(candidate) =>
						filters.pipelines.has(candidate.name) && candidate.sourceName === node.logicalName
				);
			if (!feedsSelected && (!pipeline || !filters.pipelines.has(pipeline))) return false;
		}
		if (filters.kinds.size && !filters.kinds.has(nodeKind(node))) return false;
		if (filters.statuses.size && !filters.statuses.has(node.status)) return false;
		if (filters.anchorsOnly && node.anchor !== 'eligible') return false;
		return true;
	}

	/** Filtering narrows the rendered subgraph; edges survive only if both ends do. */
	const graph = $derived.by((): Graph => {
		if (filterCount(filters) === 0) return fullGraph;
		const kept = new Set(fullGraph.nodes.filter(matches).map((node) => node.id));
		return {
			nodes: fullGraph.nodes.filter((node) => kept.has(node.id)),
			edges: fullGraph.edges.filter((edge) => kept.has(edge.source) && kept.has(edge.target))
		};
	});

	let selectedId = $state<string | null>(null);
	let selectedIds = $state<Set<string>>(new Set());
	let fitView = $state<((options?: FitOptions) => void) | undefined>();
	let runOpen = $state<boolean>(false);

	/** The graph selection seeds the run panel's --select flags (models only). */
	const runSelection = $derived.by((): string[] => {
		return [
			...new Set(
				graph.nodes
					.filter((node) => selectedIds.has(node.id) && node.logicalType !== 'source')
					.map((node) => node.logicalName)
			)
		];
	});
	// Lanes is the default: it fits the viewport ~30% larger than boxes on the
	// same graph, and its bounding box stays near viewport aspect because lane
	// width is pinned to the deepest chain while pipeline count grows downward.
	// Boxes pad every group and then pack them side by side, so they sprawl
	// horizontally along the axis there is least room on.
	const groupMode = $derived.by((): 'none' | 'boxes' | 'lanes' => {
		const groupParam: string | null = page.url.searchParams.get('group');
		return groupParam === 'boxes' ? 'boxes' : groupParam === 'none' ? 'none' : 'lanes';
	});
	let cyclicPairs = $state<[string, string][]>([]);
	let canvas = $state<{ relayout: () => void; clearSelection: () => void } | undefined>();

	const selectedNode = $derived<GraphNode | null>(
		selectedId ? (graph.nodes.find((node) => node.id === selectedId) ?? null) : null
	);
	let inspectorWasOpen = false;

	$effect(() => {
		const inspectorOpen = selectedNode !== null;
		if (inspectorOpen && !inspectorWasOpen) {
			requestAnimationFrame(() => fitView?.(DEFAULT_FIT));
		}
		inspectorWasOpen = inspectorOpen;
	});

	function resetLayout(): void {
		canvas?.relayout();
		inspectorWidth = 460;
		queueMicrotask(() => fitView?.(DEFAULT_FIT));
	}

	function setGroupMode(next: 'none' | 'boxes' | 'lanes'): void {
		const url = new URL(page.url);
		if (next === 'lanes') url.searchParams.delete('group');
		else url.searchParams.set('group', next);
		void goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	}

	function setMode(next: GraphMode): void {
		const url = new URL(page.url);
		if (next === 'logical') url.searchParams.delete('mode');
		else url.searchParams.set('mode', next);
		void goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	}

	// ── inspector resize ──────────────────────────────────────────────────────
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

	// ── status counts ─────────────────────────────────────────────────────────
	const counts = $derived.by(() => {
		let fresh = 0;
		let lagging = 0;
		let stalled = 0;
		let drift = 0;
		for (const node of graph.nodes) {
			if (node.status === 'fresh') fresh += 1;
			if (node.status === 'lagging') lagging += 1;
			if (node.status === 'stalled') stalled += 1;
			if (node.status === 'drift') drift += 1;
		}
		return { fresh, lagging, stalled, drift };
	});
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
	</div>

	<div class="flex min-h-0 flex-1 flex-col overflow-y-auto md:flex-row md:overflow-hidden">
		<!-- canvas -->
		<div class="min-h-[360px] min-w-0 flex-1">
			<LineageCanvas
				bind:this={canvas}
				{project}
				{graph}
				{groupMode}
				layoutSalt={mode}
				bind:selectedId
				bind:selectedIds
				bind:fitView
				onCycles={(pairs) => (cyclicPairs = pairs)}
			/>
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
