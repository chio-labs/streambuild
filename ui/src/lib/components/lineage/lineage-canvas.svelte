<script lang="ts">
	import {
		SvelteFlow,
		Background,
		Controls,
		type Node,
		type Edge,
		type NodeTypes
	} from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import StreamNode from '$lib/components/lineage/stream-node.svelte';
	import GroupNode from '$lib/components/lineage/group-node.svelte';
	import CollapsedGroupNode from '$lib/components/lineage/collapsed-group-node.svelte';
	import LaneNode from '$lib/components/lineage/lane-node.svelte';
	import GroupLabelOverlay from '$lib/components/lineage/group-label-overlay.svelte';
	import type { OverlayLabel } from '$lib/components/lineage/group-label-overlay.svelte';
	import FlowController from '$lib/lineage/flow-controller.svelte';
	import { DEFAULT_FIT, type FitOptions } from '$lib/lineage/flow-controller.svelte';
	import { layoutGraph } from '$lib/lineage/layout';
	import {
		detectGroupCycles,
		findBackEdges,
		groupNodeId,
		layoutGrouped,
		type GroupBox
	} from '$lib/lineage/group-layout';
	import { laneNodeId, layoutLanes } from '$lib/lineage/lane-layout';
	import { neighbourEdgeIds, tracePath } from '$lib/lineage/trace';
	import { nodeFields } from '$lib/lineage/node-fields.svelte';
	import { modelByName } from '$lib/domain/derive';
	import type { Graph, GraphNode, ModelStatus, Project, RefType } from '$lib/domain/types';

	type Props = {
		project: Project;
		/** Already filtered by the parent. */
		graph: Graph;
		/** 'none' | 'boxes' | 'lanes' — how pipeline membership is shown. */
		groupMode?: 'none' | 'boxes' | 'lanes';
		compactNodes?: boolean;
		/** Extra key mixed into the relayout trigger, e.g. the parent's mode. */
		layoutSalt?: string;
		selectedId?: string | null;
		/** Rendered held-back: in view for context, but not acted on. */
		mutedIds?: Set<string>;
		/** Rendered as directly asked for, rather than pulled in by consequence. */
		emphasisIds?: Set<string>;
		/** Context-specific per-node facts, keyed by node id. */
		notes?: Map<string, { text: string; tone: 'info' | 'warn' }>;
		/**
		 * Embedded in a scrolling page rather than owning the viewport.
		 *
		 * A canvas that owns the viewport can take the wheel for zoom. One sitting
		 * inside a scrolling page must not: the wheel belongs to the page, and
		 * stealing it traps the reader the moment the pointer crosses the graph.
		 * Zoom moves to ctrl/cmd + wheel, which browsers report as a pinch.
		 */
		embedded?: boolean;
		fitView?: ((opts?: FitOptions) => void) | undefined;
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
		mutedIds,
		emphasisIds,
		notes,
		embedded = false,
		fitView = $bindable(undefined),
		onCycles
	}: Props = $props();

	const nodeTypes: NodeTypes = {
		stream: StreamNode,
		group: GroupNode,
		collapsedGroup: CollapsedGroupNode,
		lane: LaneNode
	};

	const grouped = $derived(groupMode !== 'none');

	let collapsed = $state<Set<string>>(new Set());
	let hoveredId = $state<string | null>(null);

	function toggleGroup(groupKey: string): void {
		const next = new Set(collapsed);
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
	const groupKeyByNodeId = $derived.by((): Map<string, string> => {
		const map = new Map<string, string>();
		if (!grouped) return map;

		const consumersBySource = new Map<string, Set<string>>();
		for (const model of project.models) {
			for (const ref of model.refs) {
				if (!ref.isSource) continue;
				const bucket: Set<string> = consumersBySource.get(ref.name) ?? new Set<string>();
				bucket.add(model.pipeline);
				consumersBySource.set(ref.name, bucket);
			}
		}

		for (const node of graph.nodes) {
			if (node.logicalType === 'source') {
				const consumers: Set<string> = consumersBySource.get(node.logicalName) ?? new Set();
				const visible: string[] = [...consumers].filter((pipeline) =>
					graph.nodes.some(
						(candidate) => modelByName(project, candidate.logicalName)?.pipeline === pipeline
					)
				);
				map.set(node.id, visible.length === 1 ? visible[0] : '__shared_sources__');
				continue;
			}
			const pipeline: string | undefined = modelByName(project, node.logicalName)?.pipeline;
			map.set(node.id, pipeline ?? '__ungrouped__');
		}
		return map;
	});

	const groupLabel = (key: string): string =>
		key === '__shared_sources__' ? 'shared sources' : key === '__ungrouped__' ? 'ungrouped' : key;

	// ── flow state ────────────────────────────────────────────────────────────
	let flowNodes = $state.raw<Node[]>([]);
	let flowEdges = $state.raw<Edge[]>([]);
	let boxes = $state.raw<GroupBox[]>([]);
	let overlayLabels = $state.raw<OverlayLabel[]>([]);
	let appliedKey = $state<string>('');

	/** Terminal views are the only nodes whose every input is equally load-bearing. */
	const viewTargets = $derived(
		new Set<string>(
			graph.nodes.filter((node) => node.logicalType === 'view').map((node) => node.id)
		)
	);

	function edgeClass(
		type: RefType,
		flowing: boolean,
		dimmed: boolean,
		back: boolean,
		intoView: boolean = false
	): string {
		if (dimmed) return 'sb-edge-dimmed';
		const base =
			type === 'mutable_reference'
				? 'sb-edge-mutable'
				: type === 'reference'
					? // StreamBuild types EVERY ref of a view as `reference` — a view has no
						// driving input because there is no materialized view to trigger. But
						// that makes the two cases look identical, and they are not: a side
						// reference is a lookup, whereas a view's refs ARE the view. Drawn at
						// full weight so a terminal view does not read as barely attached.
						intoView
						? 'sb-edge-view-read'
						: 'sb-edge-reference'
					: flowing
						? 'sb-edge-driving-flowing'
						: 'sb-edge-driving';
		// Against-rank cross-box edges get routed clear of the boxes so they read
		// as deliberate rather than as a tangle.
		return back ? `${base} sb-edge-back` : base;
	}

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
			graph.edges.length,
			graph.nodes.map((node) => node.id).join('|').length,
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
		const width: number = compactNodes ? 186 : 248;
		const height: number = compactNodes ? 56 : 112;

		if (!grouped) {
			const nextNodes: Node[] = graph.nodes.map((node) => ({
				id: node.id,
				type: 'stream',
				position: { x: 0, y: 0 },
				data: {
					...node,
					compact: compactNodes,
					muted: mutedIds?.has(node.id) ?? false,
					emphasis: emphasisIds?.has(node.id) ?? false,
					note: notes?.get(node.id)
				} as unknown as Record<string, unknown>
			}));
			const nextEdges: Edge[] = graph.edges.map((edge) => ({
				id: edge.id,
				source: edge.source,
				target: edge.target,
				class: edgeClass(edge.type, edge.flowing, false, false, viewTargets.has(edge.target))
			}));
			flowNodes = layoutGraph(nextNodes, nextEdges, {
				rankSep: compactNodes ? 96 : 150,
				nodeSep: compactNodes ? 22 : 30,
				assumedWidth: width
			});
			flowEdges = nextEdges;
			boxes = [];
			overlayLabels = [];
			onCycles?.([]);
			return;
		}

		const keyOf = (nodeId: string): string | undefined => groupKeyByNodeId.get(nodeId);

		if (groupMode === 'lanes') {
			const laneNodes: Node[] = graph.nodes.map((node) => ({
				id: node.id,
				type: 'stream',
				position: { x: 0, y: 0 },
				data: {
					...node,
					compact: compactNodes,
					muted: mutedIds?.has(node.id) ?? false,
					emphasis: emphasisIds?.has(node.id) ?? false,
					note: notes?.get(node.id)
				} as unknown as Record<string, unknown>
			}));
			const laneEdges: Edge[] = graph.edges.map((edge) => ({
				id: edge.id,
				source: edge.source,
				target: edge.target
			}));

			const laid = layoutLanes(
				laneNodes,
				laneEdges,
				(node) => keyOf(node.id) ?? '__ungrouped__',
				{
					rankSep: compactNodes ? 96 : 130,
					nodeSep: compactNodes ? 22 : 28,
					assumedWidth: width,
					assumedHeight: height
				}
			);

			const bands: Node[] = laid.lanes.map((lane) => ({
				id: lane.id,
				type: 'lane',
				position: { x: lane.x, y: lane.y },
				width: lane.width,
				height: lane.height,
				selectable: false,
				draggable: false,
				zIndex: -1,
				data: { groupKey: lane.groupKey, index: lane.index } as unknown as Record<string, unknown>
			}));

			overlayLabels = laid.lanes.map((lane) => ({
				groupKey: lane.groupKey,
				label: groupLabel(lane.groupKey),
				sublabel:
					project.pipelines.find((pipeline) => pipeline.name === lane.groupKey)?.boundaryMode ??
					null,
				modelCount: graph.nodes.filter((node) => keyOf(node.id) === lane.groupKey).length,
				x: lane.x,
				y: lane.y,
				width: lane.width,
				collapsible: false
			}));
			flowNodes = [...bands, ...laid.nodes];
			flowEdges = graph.edges.map((edge) => ({
				id: edge.id,
				source: edge.source,
				target: edge.target,
				class: edgeClass(edge.type, edge.flowing, false, false, viewTargets.has(edge.target))
			}));
			boxes = [];
			onCycles?.([]);
			return;
		}

		const collapsedKeys: Set<string> = collapsed;

		// Nodes inside a collapsed group are replaced by the group itself.
		const visibleNodes: GraphNode[] = graph.nodes.filter(
			(node) => !collapsedKeys.has(keyOf(node.id) ?? '')
		);

		const remap = (nodeId: string): string => {
			const key: string | undefined = keyOf(nodeId);
			return key && collapsedKeys.has(key) ? `collapsed:${key}` : nodeId;
		};

		const seenEdge = new Set<string>();
		const remappedEdges: { id: string; source: string; target: string; type: RefType; flowing: boolean }[] = [];
		for (const edge of graph.edges) {
			const source: string = remap(edge.source);
			const target: string = remap(edge.target);
			if (source === target) continue;
			const signature = `${source}->${target}`;
			if (seenEdge.has(signature)) continue;
			seenEdge.add(signature);
			remappedEdges.push({ id: edge.id, source, target, type: edge.type, flowing: edge.flowing });
		}

		const statusCountsByGroup = new Map<string, Record<ModelStatus, number>>();
		for (const node of graph.nodes) {
			const key: string | undefined = keyOf(node.id);
			if (!key) continue;
			const counts =
				statusCountsByGroup.get(key) ??
				({ fresh: 0, lagging: 0, stalled: 0, drift: 0, source: 0 } as Record<ModelStatus, number>);
			counts[node.status] += 1;
			statusCountsByGroup.set(key, counts);
		}

		const memberNodes: Node[] = visibleNodes.map((node) => ({
			id: node.id,
			type: 'stream',
			position: { x: 0, y: 0 },
			data: {
				...node,
				compact: compactNodes,
				muted: mutedIds?.has(node.id) ?? false,
				emphasis: emphasisIds?.has(node.id) ?? false,
				note: notes?.get(node.id)
			} as unknown as Record<string, unknown>
		}));
		const collapsedNodes: Node[] = [...collapsedKeys]
			.filter((key) => graph.nodes.some((node) => keyOf(node.id) === key))
			.map((key) => ({
				id: `collapsed:${key}`,
				type: 'collapsedGroup',
				position: { x: 0, y: 0 },
				data: {
					groupKey: key,
					label: groupLabel(key),
					sublabel: null,
					modelCount: graph.nodes.filter((node) => keyOf(node.id) === key).length,
					statusCounts: statusCountsByGroup.get(key) ?? {},
					ontoggle: toggleGroup
				} as unknown as Record<string, unknown>
			}));

		const layoutNodes: Node[] = [...memberNodes, ...collapsedNodes];
		const layoutEdges: Edge[] = remappedEdges.map((edge) => ({
			id: edge.id,
			source: edge.source,
			target: edge.target
		}));

		// A collapsed group is its own group of one, so it ranks alongside the boxes.
		const result = layoutGrouped(
			layoutNodes,
			layoutEdges,
			(node) =>
				node.id.startsWith('collapsed:')
					? node.id.slice('collapsed:'.length)
					: (keyOf(node.id) ?? '__ungrouped__'),
			{
				rankSep: compactNodes ? 96 : 130,
				nodeSep: compactNodes ? 22 : 28,
				assumedWidth: width,
				assumedHeight: height
			}
		);

		const groupOfId = (nodeId: string): string | undefined =>
			nodeId.startsWith('collapsed:') ? nodeId.slice('collapsed:'.length) : keyOf(nodeId);

		const back: Set<string> = findBackEdges(layoutEdges, result.boxes, groupOfId);
		onCycles?.(detectGroupCycles(layoutEdges, groupOfId));

		// Group containers must precede their children in the node array.
		const containers: Node[] = result.boxes
			.filter((box) => !collapsedKeys.has(box.groupKey))
			.map((box) => ({
				id: box.id,
				type: 'group',
				position: { x: box.x, y: box.y },
				width: box.width,
				height: box.height,
				selectable: false,
				draggable: false,
				zIndex: -1,
				data: { groupKey: box.groupKey } as unknown as Record<string, unknown>
			}));

		// Collapsed groups are plain nodes: strip the parent wrapper.
		const positioned: Node[] = result.nodes.map((node) => {
			if (!node.id.startsWith('collapsed:')) return node;
			const box = result.boxes.find((candidate) => candidate.groupKey === node.id.slice(10));
			return {
				...node,
				parentId: undefined,
				extent: undefined,
				position: box ? { x: box.x, y: box.y } : node.position
			};
		});

		overlayLabels = result.boxes
			.filter((box) => !collapsedKeys.has(box.groupKey))
			.map((box) => ({
				groupKey: box.groupKey,
				label: groupLabel(box.groupKey),
				sublabel:
					project.pipelines.find((pipeline) => pipeline.name === box.groupKey)?.boundaryMode ?? null,
				modelCount: graph.nodes.filter((node) => keyOf(node.id) === box.groupKey).length,
				x: box.x,
				y: box.y,
				width: box.width,
				collapsible: true
			}));
		flowNodes = [...containers, ...positioned];
		flowEdges = remappedEdges.map((edge) => ({
			id: edge.id,
			source: edge.source,
			target: edge.target,
			class: edgeClass(edge.type, edge.flowing, false, back.has(edge.id), viewTargets.has(edge.target))
		}));
		boxes = result.boxes;
	}

	// ── highlight ─────────────────────────────────────────────────────────────
	const litEdgeIds = $derived.by((): Set<string> | null => {
		if (selectedId) return tracePath(new Set([selectedId]), flowEdges).edges;
		if (hoveredId) return neighbourEdgeIds(hoveredId, flowEdges);
		return null;
	});

	$effect(() => {
		const lit: Set<string> | null = litEdgeIds;
		const domainById = new Map(graph.edges.map((edge) => [edge.id, edge]));
		let changed = false;
		const next: Edge[] = flowEdges.map((edge) => {
			const domainEdge = domainById.get(edge.id);
			if (!domainEdge) return edge;
			const dimmed: boolean = lit !== null && !lit.has(edge.id);
			const wasBack: boolean = (edge.class ?? '').includes('sb-edge-back');
			const nextClass: string = edgeClass(
				domainEdge.type,
				domainEdge.flowing,
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
		const target = event.target as HTMLElement | null;
		const host = target?.closest<HTMLElement>('.svelte-flow__node');
		const id: string | undefined = host?.dataset.id;
		if (!id || id.startsWith('group:') || id.startsWith('lane:')) return null;
		return id;
	}

	function onCanvasClick(event: Event): void {
		const id: string | null = nodeIdFromEvent(event);
		selectedId = id === selectedId ? null : id;
	}

	function onCanvasHover(event: Event): void {
		hoveredId = nodeIdFromEvent(event);
	}

	export function relayout(): void {
		appliedKey = '';
	}
</script>

<div
	class="h-full w-full"
	role="presentation"
	onclick={onCanvasClick}
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
		zoomOnScroll={!embedded}
		preventScrolling={!embedded}
		proOptions={{ hideAttribution: true }}
	>
		<Background bgColor="var(--background)" patternColor="var(--sb-grid)" gap={22} />
		<Controls showLock={false} />
		<FlowController bind:fitView />
		<GroupLabelOverlay labels={overlayLabels} ontoggle={toggleGroup} />
	</SvelteFlow>
</div>
