<script lang="ts">
	import LineageCanvas from '$lib/presentation/components/lineage/lineage-canvas.svelte';
	import EdgeLegend from '$lib/presentation/components/lineage/edge-legend.svelte';
	import { buildLogicalGraph } from '$lib/domain/main/graphs/build-logical-graph';
	import type { Project } from '$lib/domain/types';
	import type { Graph } from '$lib/lineage/types';

	type Props = { project: Project; pipelineName: string; height?: string };
	let { project, pipelineName, height = '520px' }: Props = $props();

	/**
	 * The project graph narrowed to one pipeline plus one hop out, so side
	 * references stay visible — they are exactly what the tree view cannot show.
	 */
	const scoped = $derived.by((): Graph => {
		const full: Graph = buildLogicalGraph(project);
		const members = new Set<string>(
			project.models.filter((model) => model.pipeline === pipelineName).map((model) => model.name)
		);

		const keep = new Set<string>();
		for (const node of full.nodes) {
			if (node.logicalType !== 'source' && members.has(node.logicalName)) keep.add(node.id);
		}
		for (const edge of full.edges) {
			if (keep.has(edge.target)) keep.add(edge.source);
		}

		return {
			nodes: full.nodes.filter((node) => keep.has(node.id)),
			edges: full.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target))
		};
	});
</script>

<div class="overflow-hidden rounded-[4px] border border-border">
	<div class="flex items-center gap-3 border-b border-border px-3 py-1.5">
		<EdgeLegend compact />
	</div>
	<div style:height>
		<!-- Boxes are off here: a single pipeline needs no membership cue, and the
		     one-hop neighbours read better as plain cross-pipeline nodes. -->
		<LineageCanvas {project} graph={scoped} groupMode="none" layoutSalt={pipelineName} />
	</div>
</div>
