<script lang="ts">
	import { SvelteFlow, Background, Controls } from '@xyflow/svelte';
	import type * as XYFlow from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import GroupLabelOverlay, {
		type OverlayLabel
	} from '$lib/presentation/components/lineage/group-label-overlay.svelte';
	import FlowController, {
		DEFAULT_FIT
	} from '$lib/presentation/components/lineage/flow-controller.svelte';
	import {
		buildFlowLayout,
		buildGroupKeyByNodeId,
		type FlowLayoutResult
	} from '$lib/presentation/_helpers/lineage/flow-layout';
	import {
		graphTopologyKey,
		refreshFlowEdges,
		refreshFlowNodes
	} from '$lib/presentation/_helpers/lineage/flow-presentation';
	import { LINEAGE_NODE_TYPES } from '$lib/presentation/_helpers/lineage/node-types';
	import { neighbourEdgeIds, tracePath } from '$lib/presentation/_helpers/lineage/trace';
	import { getNodeFields } from '$lib/lineage/main/get-node-fields';
	import type { Project } from '$lib/domain/types';
	import type { GroupMode } from '$lib/lineage/types';

	const nodeFields = getNodeFields();

	type Props = {
		project: Project;
		/** Already filtered by the parent. */
		graph: import('$lib/lineage/types').Graph;
		/** 'none' | 'boxes' | 'lanes' — how pipeline membership is shown. */
		groupMode?: GroupMode;
		compactNodes?: boolean;
		collapseGroupsByDefault?: boolean;
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
		collapseGroupsByDefault = false,
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
	function initialCollapsedGroups(): Set<string> {
		if (!collapseGroupsByDefault || groupMode !== 'boxes') return new Set();
		return new Set(buildGroupKeyByNodeId(project, graph, true).values());
	}

	let collapsed = $state<Set<string>>(initialCollapsedGroups());
	let expandedGroups = $state<Set<string>>(new Set());
	let hoveredId = $state<string | null>(null);

	function toggleGroup(groupKey: string): void {
		const next: Set<string> = new Set(collapsed);
		const nextExpanded: Set<string> = new Set(expandedGroups);
		if (effectiveCollapsed.has(groupKey)) {
			next.delete(groupKey);
			nextExpanded.add(groupKey);
		} else {
			next.add(groupKey);
			nextExpanded.delete(groupKey);
		}
		collapsed = next;
		expandedGroups = nextExpanded;
	}

	const groupKeyByNodeId = $derived(buildGroupKeyByNodeId(project, graph, grouped));
	const effectiveCollapsed = $derived.by((): Set<string> => {
		const next: Set<string> = new Set(collapsed);
		if (!collapseGroupsByDefault || groupMode !== 'boxes') return next;
		for (const groupKey of groupKeyByNodeId.values()) {
			if (!expandedGroups.has(groupKey)) next.add(groupKey);
		}
		return next;
	});

	let flowNodes = $state.raw<XYFlow.Node[]>([]);
	let flowEdges = $state.raw<XYFlow.Edge[]>([]);
	let overlayLabels = $state.raw<OverlayLabel[]>([]);
	let appliedKey = $state<string>('');

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
			graphTopologyKey(graph.nodes, graph.edges),
			[...groupKeyByNodeId].map(([id, group]) => `${id}:${group}`).join('|'),
			[...effectiveCollapsed].sort().join(','),
			Object.entries(nodeFields.value)
				.filter(([, on]) => on)
				.map(([key]) => key)
				.join(',')
		].join('~')
	);
	const nodePresentationKey = $derived(
		graph.nodes
			.map(
				(node) =>
					`${node.id}:${node.status}:${node.rows}:${node.rowsPerSecond}:${node.failingChecks}:` +
					`${node.warningChecks}:${node.totalChecks}:${node.drift}:${node.anchor}`
			)
			.join('|')
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
				collapsed: effectiveCollapsed,
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

	const litEdgeIds = $derived.by((): Set<string> | null => {
		if (selectedIds.size) return tracePath(selectedIds, flowEdges).edges;
		if (hoveredId) return neighbourEdgeIds(hoveredId, flowEdges);
		return null;
	});
	const domainNodes = $derived(new Map(graph.nodes.map((node) => [node.id, node])));
	const domainEdges = $derived(new Map(graph.edges.map((edge) => [edge.id, edge])));
	let appliedNodePresentationKey = $state<string>('');
	let appliedEdgePresentationKey = $state<string>('');

	$effect(() => {
		const key: string = `${layoutKey}~${nodePresentationKey}`;
		if (key === appliedNodePresentationKey) return;
		appliedNodePresentationKey = key;
		const refreshed: XYFlow.Node[] = refreshFlowNodes({
			nodes: flowNodes,
			edges: flowEdges,
			domainNodes,
			domainEdges,
			groupKeyByNodeId,
			viewTargets,
			litEdgeIds
		});
		if (refreshed !== flowNodes) flowNodes = refreshed;
	});

	$effect(() => {
		const lit: Set<string> | null = litEdgeIds;
		const key: string = `${layoutKey}~${graph.edges
			.map((edge) => `${edge.id}:${edge.flowState}`)
			.join('|')}~${lit === null ? '' : [...lit].sort().join('|')}`;
		if (key === appliedEdgePresentationKey) return;
		appliedEdgePresentationKey = key;
		const refreshed: XYFlow.Edge[] = refreshFlowEdges({
			nodes: flowNodes,
			edges: flowEdges,
			domainNodes,
			domainEdges,
			groupKeyByNodeId,
			viewTargets,
			litEdgeIds: lit
		});
		if (refreshed !== flowEdges) flowEdges = refreshed;
	});
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

	function hoverNode(node: XYFlow.Node): void {
		if (node.id.startsWith('group:') || node.id.startsWith('lane:')) return;
		hoveredId = node.id;
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
	class:sb-static-flow={flowNodes.length > 150}
	data-testid="lineage-canvas"
	data-node-count={flowNodes.length}
	data-compact={compactNodes}
	data-viewport-culling={flowNodes.length > 150}
	role="presentation"
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
		onlyRenderVisibleElements={flowNodes.length > 150}
		preventScrolling={!embedded}
		multiSelectionKey={['Meta', 'Control', 'Shift']}
		onselectionchange={onSelectionChange}
		onnodeclick={({ node }) => (selectedId = node.id)}
		onnodepointerenter={({ node }) => hoverNode(node)}
		onnodepointerleave={({ node }) => {
			if (hoveredId === node.id) hoveredId = null;
		}}
		proOptions={{ hideAttribution: true }}
	>
		<Background bgColor="var(--background)" patternColor="var(--sb-grid)" gap={22} />
		<Controls showLock={false} />
		<FlowController bind:fitView />
		<GroupLabelOverlay labels={overlayLabels} ontoggle={toggleGroup} />
	</SvelteFlow>
</div>
