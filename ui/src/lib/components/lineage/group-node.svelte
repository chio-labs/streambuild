<script module lang="ts">
	export type GroupNodeData = { groupKey: string };
</script>

<script lang="ts">
	import type { NodeProps } from '@xyflow/svelte';

	// Chrome only: a bordered well. The name, count and collapse control live in
	// GroupLabelOverlay, drawn OUTSIDE the canvas transform so they keep a constant
	// screen size. An in-canvas header band would either shrink its text into
	// illegibility or (if counter-scaled) burst out of the band and collide with
	// the nodes below.
	//
	// Declared so the component satisfies Svelte Flow's NodeTypes contract.
	// eslint-disable-next-line @typescript-eslint/no-unused-vars
	let _props: NodeProps = $props();
</script>

<div
	class="pointer-events-none h-full w-full rounded-[7px] border-2"
	style:border-color="var(--sb-group-border)"
	style:background="var(--sb-group-fill)"
></div>
