<script lang="ts">
	import { SvelteFlow, Background, Controls } from '@xyflow/svelte';
	import type * as XYFlow from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import GroupLabelOverlay from '$lib/presentation/components/lineage/group-label-overlay.svelte';
	import type { OverlayLabel } from '$lib/presentation/components/lineage/group-label-overlay.svelte';
	import FlowController from '$lib/presentation/components/lineage/flow-controller.svelte';
	import { DEFAULT_FIT } from '$lib/presentation/components/lineage/flow-controller.svelte';
	import {
		buildFlowLayout,
		buildGroupKeyByNodeId,
		edgeClass,
		type FlowLayoutResult,
		type GroupMode
	} from '$lib/presentation/_helpers/lineage/flow-layout';
	import { LINEAGE_NODE_TYPES } from '$lib/presentation/_helpers/lineage/node-types';
	import { neighbourEdgeIds, tracePath } from '$lib/presentation/_helpers/lineage/trace';
	import { getNodeFields } from '$lib/lineage/main/get-node-fields';
	import type { Project } from '$lib/domain/types';
	import type { Graph, GraphEdge } from '$lib/lineage/types';

	const nodeFields = getNodeFields();

	type Props = {
		project: Project;
		/** Already filtered by the parent. */
		graph: Graph;
		/** 'none' | 'boxes' | 'lanes' — how pipeline membership is shown. */
		groupMode?: GroupMode;
		compactNodes?: boolean;
		/** Extra key mixed into the relayout trigger, e.g. the parent's mode. */
		layoutSalt?: string;
		selectedId?: string | null;
		selectedIds?: Set<string>;
		/** Rendered held-back: in view for context, but not acted on. */
		mutedIds?: Set<string>;
		/** Rendered as directly asked for, rather than pulled in by consequence. */
		emphasisIds?: Set<string>;
		/** Context-specific per-node facts, keyed by node id. */
		notes?: Map<string, { text: string; tone: 'info' | 'warn' }>;
		/** Embedded graphs leave ordinary wheel scrolling to their parent page. */
		embedded?: boolean;
		fitView?:
			| ((opts?: { duration?: number; padding?: number; minZoom?: number; maxZoom?: number }) => void)
			| undefined;
		/** Pipelines whose members are never grouped away (embedded single-pipeline use). */
		onCycles?: (pairs: [string, string][]) => void;
	};

	let {
		project,
		graph,
		groupMode = 'none',
		compactNodes = false,
		layoutSalt = '',
		selectedId = $bindable(null),
		selectedIds = $bindable(new Set<string>()),
		mutedIds,
		emphasisIds,
		notes,
		embedded = false,
		fitView = $bindable(undefined),
		onCycles
	}: Props = $props();

	const nodeTypes: XYFlow.NodeTypes = LINEAGE_NODE_TYPES;

	const grouped = $derived(groupMode !== 'none');

	let collapsed = $state<Set<string>>(new Set());
	let hoveredId = $state<string | null>(null);

	function toggleGroup(groupKey: string): void {
		const next: Set<string> = new Set(collapsed);
		if (next.has(groupKey)) next.delete(groupKey);
		else next.add(groupKey);
		collapsed = next;
	}

	// ── grouping ──────────────────────────────────────────────────────────────
	/**
	 * A model belongs to its pipeline. A source has no pipeline of its own, so it
	 * joins the single pipeline it feeds — which reads correctly and matches the
	 * pipeline page's mental model. A source feeding several pipelines goes to a
	 * shared box rather than being arbitrarily assigned to one.
	 */
	const groupKeyByNodeId = $derived(buildGroupKeyByNodeId(project, graph, grouped));

	// ── flow state ────────────────────────────────────────────────────────────
	let flowNodes = $state.raw<XYFlow.Node[]>([]);
	let flowEdges = $state.raw<XYFlow.Edge[]>([]);
	let overlayLabels = $state.raw<OverlayLabel[]>([]);
	let appliedKey = $state<string>('');

	/** Terminal views are the only nodes whose every input is equally load-bearing. */
	const viewTargets = $derived(
		new Set<string>(
			graph.nodes.filter((node) => node.logicalType === 'view').map((node) => node.id)
		)
	);

	const layoutKey = $derived(
		[
			layoutSalt,
			groupMode,
			compactNodes ? 'compact' : 'full',
			mutedIds?.size ?? 0,
			emphasisIds?.size ?? 0,
			// Content, not size: a note flipping from 'rebuilding…' to '554k rows'
			// must re-render even though the map cardinality is unchanged.
			[...(notes ?? new Map())].map(([id, note]) => `${id}=${note.text}`).join('|'),
			graph.nodes.length,
			graph.nodes.map((node) => node.id).join('|').length,
			graph.edges.map((edge) => `${edge.id}:${edge.type}:${edge.flowState}`).join('|'),
			[...collapsed].sort().join(','),
			Object.entries(nodeFields.value)
				.filter(([, on]) => on)
				.map(([key]) => key)
				.join(',')
		].join('~')
	);

	// Relayout only on a stable key — never on `nodes` — or the effect re-triggers
	// itself and wedges the main thread (blank page).
	$effect(() => {
		const key: string = layoutKey;
		if (key === appliedKey) return;
		appliedKey = key;
		rebuild();
	});

	function rebuild(): void {
		const result: FlowLayoutResult = buildFlowLayout(
			{
				project,
				graph,
				groupMode,
				compactNodes,
				selectedIds,
				mutedIds,
				emphasisIds,
				notes,
				collapsed,
				groupKeyByNodeId,
				viewTargets
			},
			toggleGroup
		);
		flowNodes = result.nodes;
		flowEdges = result.edges;
		overlayLabels = result.overlayLabels;
		onCycles?.(result.cycles);
	}

	// ── highlight ─────────────────────────────────────────────────────────────
	const litEdgeIds = $derived.by((): Set<string> | null => {
		if (selectedIds.size) return tracePath(selectedIds, flowEdges).edges;
		if (hoveredId) return neighbourEdgeIds(hoveredId, flowEdges);
		return null;
	});

	$effect(() => {
		const lit: Set<string> | null = litEdgeIds;
		const domainById: Map<string, GraphEdge> = new Map(
			graph.edges.map((edge) => [edge.id, edge])
		);
		let changed: boolean = false;
		const next: XYFlow.Edge[] = flowEdges.map((edge) => {
			const domainEdge: GraphEdge | undefined = domainById.get(edge.id);
			if (!domainEdge) return edge;
			const dimmed: boolean = lit !== null && !lit.has(edge.id);
			const wasBack: boolean = (edge.class ?? '').includes('sb-edge-back');
			const nextClass: string = edgeClass(
				domainEdge.type,
				domainEdge.flowState,
				dimmed,
				wasBack,
				viewTargets.has(domainEdge.target)
			);
			if (nextClass === edge.class) return edge;
			changed = true;
			return { ...edge, class: nextClass };
		});
		if (changed) flowEdges = next;
	});

	function nodeIdFromEvent(event: Event): string | null {
		const target: HTMLElement | null = event.target as HTMLElement | null;
		const host: HTMLElement | null | undefined = target?.closest<HTMLElement>('.svelte-flow__node');
		const id: string | undefined = host?.dataset.id;
		if (!id || id.startsWith('group:') || id.startsWith('lane:')) return null;
		return id;
	}


	const onSelectionChange: XYFlow.OnSelectionChange = ({ nodes }): void => {
		const nextIds: Set<string> = new Set(
			nodes
				.map((node) => node.id)
				.filter(
					(id) =>
						!id.startsWith('group:') && !id.startsWith('lane:') && !id.startsWith('collapsed:')
				)
		);
		selectedIds = nextIds;
		if (selectedId === null || !nextIds.has(selectedId)) {
			selectedId = nodes.at(-1)?.id ?? null;
		}
	};

	function onCanvasHover(event: Event): void {
		hoveredId = nodeIdFromEvent(event);
	}

	export function relayout(): void {
		appliedKey = '';
	}

	export function clearSelection(): void {
		selectedId = null;
		selectedIds = new Set();
		flowNodes = flowNodes.map((node) => (node.selected ? { ...node, selected: false } : node));
	}
</script>

<div
	class="h-full w-full"
	data-testid="lineage-canvas"
	role="presentation"
	onmouseover={onCanvasHover}
	onmouseout={() => (hoveredId = null)}
	onfocus={onCanvasHover}
	onblur={() => (hoveredId = null)}
>
	<SvelteFlow
		bind:nodes={flowNodes}
		bind:edges={flowEdges}
		{nodeTypes}
		fitView
		fitViewOptions={DEFAULT_FIT}
		minZoom={0.15}
		maxZoom={1.8}
		zoomOnScroll={false}
		zoomActivationKey={['Meta', 'Control']}
		panOnScroll={!embedded}
		preventScrolling={!embedded}
		multiSelectionKey={['Meta', 'Control', 'Shift']}
		onselectionchange={onSelectionChange}
		onnodeclick={({ node }) => (selectedId = node.id)}
		proOptions={{ hideAttribution: true }}
	>
		<Background bgColor="var(--background)" patternColor="var(--sb-grid)" gap={22} />
		<Controls showLock={false} />
		<FlowController bind:fitView />
		<GroupLabelOverlay labels={overlayLabels} ontoggle={toggleGroup} />
	</SvelteFlow>
</div>
