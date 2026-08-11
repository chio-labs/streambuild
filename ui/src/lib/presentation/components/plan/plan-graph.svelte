<script lang="ts">
	import LineageCanvas from '$lib/presentation/components/lineage/lineage-canvas.svelte';
	import { DEFAULT_FIT, type FitOptions } from '$lib/presentation/components/lineage/flow-controller.svelte';
	import ChevronsUpDownIcon from '@lucide/svelte/icons/chevrons-up-down';
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import EdgeLegend from '$lib/presentation/components/lineage/edge-legend.svelte';
	import { buildLogicalGraph } from '$lib/domain/main/graphs/build-logical-graph';
	import { modelByName } from '$lib/domain/main/lookups/model-by-name';
	import type { Project } from '$lib/domain/types';
	import type { Graph, GraphNode } from '$lib/lineage/types';
	import type { Plan } from '$lib/planning/types';

	type Props = {
		project: Project;
		plan: Plan;
	};
	let { project, plan }: Props = $props();

	/**
	 * A full plan's closure measures ~1030x610, an aspect of about 1.7, while
	 * this panel is far wider than it is tall. The graph is therefore always
	 * height-bound: at 300px it can only ever reach 0.45 zoom, which renders the
	 * node labels too small to read. 400px is the smallest height that keeps
	 * them legible without pushing the scope tables off the fold, and expanding
	 * trades that fold for a graph worth studying.
	 */
	const FULL_HEIGHT: number = 400;
	const SMALL_HEIGHT: number = 240;
	const EXPANDED_HEIGHT: number = 680;
	/** Below this the closure is a short chain and 400px is mostly dead space. */
	const SMALL_PLAN: number = 4;
	let expanded = $state<boolean>(false);

	/**
	 * The lineage graph cut down to the plan.
	 *
	 * Two tiers, because a table can say WHICH models are in scope but not what
	 * shape the blast radius has:
	 *
	 *   selected   named by a selector
	 *   in scope   dragged in downstream — also dropped and recreated
	 *   held back  read but not rebuilt — sources and models outside the closure
	 *
	 * The held-back tier is drawn rather than filtered out. Dropping it would
	 * leave the closure looking self-rooting, hiding exactly the inputs someone
	 * checking a destructive command needs to see.
	 */
	const inScope = $derived(
		new Set<string>([
			...plan.entries.map((entry) => entry.modelName),
			...plan.phases.flatMap((phase) => phase.modelNames)
		])
	);
	/**
	 * Separating these two is the whole point of the scope card's "1 selected ·
	 * 9 downstream of selection": the second number is the one that surprises
	 * people, and only the graph shows where it goes.
	 */
	const selectedNames = $derived(
		new Set<string>(
			plan.entries.filter((entry) => entry.reason === 'selected').map((entry) => entry.modelName)
		)
	);
	const heldBack = $derived(
		new Set<string>([
			...plan.prerequisites.map((prerequisite) => prerequisite.name),
			...plan.phases.flatMap((phase) => phase.contextModelNames)
		])
	);

	const full = $derived<Graph>(buildLogicalGraph(project));

	const graph = $derived<Graph>({
		nodes: full.nodes.filter(
			(node) => inScope.has(node.logicalName) || heldBack.has(node.logicalName)
		),
		edges: full.edges.filter((edge) => {
			const source: GraphNode | undefined = full.nodes.find((node) => node.id === edge.source);
			const target: GraphNode | undefined = full.nodes.find((node) => node.id === edge.target);
			if (!source || !target) return false;
			const keep: (name: string) => boolean = (name: string): boolean =>
				inScope.has(name) || heldBack.has(name);
			return keep(source.logicalName) && keep(target.logicalName);
		})
	});

	const mutedIds = $derived(
		new Set<string>(
			graph.nodes.filter((node) => !inScope.has(node.logicalName)).map((node) => node.id)
		)
	);

	const emphasisIds = $derived(
		new Set<string>(
			graph.nodes.filter((node) => selectedNames.has(node.logicalName)).map((node) => node.id)
		)
	);

	/**
	 * Being a replay root is already visible: it is exactly a model whose driving
	 * edge arrives from a held-back node. What the shape cannot say is how the
	 * replay is BOUNDED, and that an aggregate may not honour the bound at all —
	 * so only those two facts are annotated.
	 */
	/** Prerequisites the warehouse does not actually hold — the plan would fail. */
	const missingNames = $derived(
		new Set<string>(
			plan.prerequisites
				.filter((prerequisite) => !prerequisite.present)
				.map((prerequisite) => prerequisite.name)
		)
	);

	const notes = $derived.by(() => {
		const map = new Map<string, { text: string; tone: 'info' | 'warn' }>();
		const bounded: boolean = plan.replayWindow.mode === 'from';
		for (const node of graph.nodes) {
			if (missingNames.has(node.logicalName)) {
				map.set(node.id, { text: 'missing — not in warehouse', tone: 'warn' });
				continue;
			}
			if (!inScope.has(node.logicalName)) continue;
			const root: Plan['replayRoots'][number] | undefined = plan.replayRoots.find(
				(item) => item.modelName === node.logicalName
			);
			const aggregate: boolean = modelByName(project, node.logicalName)?.isAggregate ?? false;
			// Aggregation prevents a clean split, so a start time may be ignored and
			// the whole history replayed. That is a cost surprise, not a detail.
			if (bounded && aggregate) {
				map.set(node.id, { text: 'may replay all', tone: 'warn' });
			} else if (root) {
				map.set(node.id, { text: `root · ${root.boundaryMode}`, tone: 'info' });
			}
		}
		return map;
	});

	// Selection changes the node set, so the layout must be recomputed rather
	// than reused; the canvas keys its relayout off this.
	const salt = $derived(
		`plan:${graph.nodes.length}:${mutedIds.size}:${plan.command.length}:${plan.replayWindow.mode}`
	);

	const small = $derived(graph.nodes.length <= SMALL_PLAN);
	const height = $derived(
		expanded ? EXPANDED_HEIGHT : small ? SMALL_HEIGHT : FULL_HEIGHT
	);

	let selectedId = $state<string | null>(null);
	let canvas = $state<{ relayout: () => void } | undefined>();
	let fitView = $state<((opts?: FitOptions) => void) | undefined>();

	// A programmatic fitView() does not inherit the fitViewOptions given to the
	// <SvelteFlow> attribute, so the bounds have to be restated or a small plan
	// zooms to 1.8. Sharing one constant keeps the refit framing identical to
	// the initial one.
	const FIT: FitOptions = DEFAULT_FIT;

	// Changing the selection changes the node set, and SvelteFlow's `fitView`
	// attribute only fires on init. Without this the graph keeps the previous
	// selection's pan and zoom, so a narrower plan lands off-screen.
	//
	// A plain variable, not $state: comparing against it inside the effect would
	// otherwise make the effect depend on its own write.
	let fittedSalt: string | null = null;
	$effect(() => {
		const key: string = `${salt}:${expanded}`;
		if (key === fittedSalt) return;
		const first: boolean = fittedSalt === null;
		fittedSalt = key;
		// On mount SvelteFlow's own fitView attribute has already framed the
		// graph. Refitting on top of it just animates from one frame to another,
		// which is the readjustment you see on every page load.
		if (first) return;
		// Queue behind the canvas's own layout effect.
		const timer: ReturnType<typeof setTimeout> = setTimeout(() => fitView?.(FIT), 80);
		return () => clearTimeout(timer);
	});
</script>

<div class="flex w-full flex-col border-b border-border" style:height="{height}px">
	{#if graph.nodes.length === 0}
		<div class="text-muted-foreground grid h-full place-items-center font-mono text-[11.5px]">
			nothing in scope
		</div>
	{:else}
		<!--
			A real row rather than two absolutely positioned overlays. As overlays the
			legend and the controls were laid out independently of each other, so on a
			narrower window they simply collided.
		-->
		<div
			class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--border-subtle)] px-2 py-1.5"
		>
			<span class="flex items-center gap-1.5 font-mono text-[10px]">
				<span
					class="ring-primary/70 h-[9px] w-[9px] rounded-[2px] border border-[var(--border-strong)] ring-2"
					style:background="var(--card)"
				></span>
				selected
			</span>
			<span class="flex items-center gap-1.5 font-mono text-[10px]">
				<span
					class="h-[9px] w-[9px] rounded-[2px] border border-[var(--border-strong)]"
					style:background="var(--card)"
				></span>
				downstream
			</span>
			<span class="text-[var(--sb-text-faint)] flex items-center gap-1.5 font-mono text-[10px]">
				<span
					class="h-[9px] w-[9px] rounded-[2px] border border-dashed border-[var(--border-strong)] opacity-45"
				></span>
				read, not rebuilt
			</span>
			<span class="bg-border h-[11px] w-px"></span>
			<EdgeLegend compact />

			<div class="ml-auto flex items-center gap-1.5">
				<span class="text-[var(--sb-text-faint)] hidden font-mono text-[10px] lg:inline">
					ctrl + scroll to zoom
				</span>
				<button
					class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10px]"
					onclick={() => {
						canvas?.relayout();
						setTimeout(() => fitView?.(FIT), 80);
					}}
				>
					<RotateIcon size={11} /> reset layout
				</button>
				<!-- Nothing to gain from expanding a plan that already fits: zoom is
				     capped, so the extra height would only add whitespace. -->
				{#if !small}
					<button
						class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10px]"
						onclick={() => (expanded = !expanded)}
					>
						<ChevronsUpDownIcon size={11} />
						{expanded ? 'collapse' : 'expand'}
					</button>
				{/if}
			</div>
		</div>

		<div class="min-h-0 flex-1">
			<LineageCanvas
				{project}
				{graph}
				{mutedIds}
				{emphasisIds}
			{notes}
				groupMode="none"
				compactNodes
				embedded
				layoutSalt={salt}
				bind:selectedId
				bind:fitView
				bind:this={canvas}
			/>
		</div>
	{/if}
</div>
