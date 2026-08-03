<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import MaximizeIcon from '@lucide/svelte/icons/maximize';
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import NodeFieldsPopover from '$lib/components/lineage/node-fields-popover.svelte';
	import GraphFilters, { emptyFilters, filterCount } from '$lib/components/lineage/graph-filters.svelte';
	import type { GraphFilterState, NodeKindFilter } from '$lib/components/lineage/graph-filters.svelte';
	import GraphInspector from '$lib/components/graph/graph-inspector.svelte';
	import LineageCanvas from '$lib/components/lineage/lineage-canvas.svelte';
	import EdgeLegend from '$lib/components/lineage/edge-legend.svelte';
	import { getProject } from '$lib/api';
	import { buildLogicalGraph, buildPhysicalGraph, modelByName } from '$lib/domain/derive';
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

	const fullGraph = $derived<Graph>(
		mode === 'logical' ? buildLogicalGraph(project) : buildPhysicalGraph(project)
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
	let fitView = $state<(() => void) | undefined>();
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
	let canvas = $state<{ relayout: () => void } | undefined>();

	const selectedNode = $derived<GraphNode | null>(
		selectedId ? (graph.nodes.find((node) => node.id === selectedId) ?? null) : null
	);

	function resetLayout(): void {
		canvas?.relayout();
		inspectorWidth = 460;
		queueMicrotask(() => fitView?.());
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
	<div class="flex shrink-0 items-center gap-2.5 border-b border-border px-[18px] py-2.5">
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

		<span class="text-[var(--sb-text-faint)] max-w-[380px] font-mono text-[10.5px] leading-snug">
			{#if mode === 'logical'}
				authored sources, models and typed reference edges
			{:else}
				every ClickHouse object: kafka__ → mv__ → raw__ → mv__model → tbl__model
			{/if}
		</span>

		<div class="ml-auto flex items-center gap-2.5">
			<EdgeLegend />
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
				onclick={() => fitView?.()}
			>
				<MaximizeIcon size={13} />
			</button>
		</div>
	</div>

	<!-- filters -->
	<div class="flex shrink-0 items-center gap-2 border-b border-border px-[18px] py-2">
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
		class="text-muted-foreground flex shrink-0 items-center gap-4 border-b border-border px-[18px] py-1.5 font-mono text-[10.5px]"
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

	<div class="flex min-h-0 flex-1">
		<!-- canvas -->
		<div class="min-w-0 flex-1">
			<LineageCanvas
				bind:this={canvas}
				{project}
				{graph}
				{groupMode}
				layoutSalt={mode}
				bind:selectedId
				bind:fitView
				onCycles={(pairs) => (cyclicPairs = pairs)}
			/>
		</div>

		{#if selectedNode}
			<!-- drag handle -->
			<div
				class="hover:bg-primary w-[3px] shrink-0 cursor-col-resize bg-[var(--border-subtle)] transition-colors"
				role="separator"
				aria-orientation="vertical"
				onpointerdown={startResize}
				onpointermove={onResize}
				onpointerup={endResize}
			></div>
			<div class="shrink-0 overflow-y-auto border-l border-border" style:width="{inspectorWidth}px">
				<GraphInspector node={selectedNode} {mode} onclose={() => (selectedId = null)} />
			</div>
		{/if}
	</div>
</div>
