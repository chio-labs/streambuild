<script module lang="ts">
	export type LaneNodeData = { groupKey: string; index: number };
</script>

<script lang="ts">
	import type { NodeProps } from '@xyflow/svelte';

	let { data }: NodeProps = $props();
	const lane = $derived(data as unknown as LaneNodeData);
	const striped = $derived(lane.index % 2 === 1);
</script>

<!-- Band chrome only; the label is drawn in screen space by GroupLabelOverlay. -->
<div
	class="pointer-events-none h-full w-full border-t"
	style:border-color="var(--sb-group-border)"
	style:background={striped ? 'var(--sb-lane-fill)' : 'transparent'}
></div>
