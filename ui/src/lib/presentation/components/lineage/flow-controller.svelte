<script module lang="ts">
	/**
	 * Mirrors the subset of SvelteFlow's FitViewOptions callers need. The
	 * `fitView` ATTRIBUTE on <SvelteFlow> applies fitViewOptions, but a
	 * programmatic fitView() call does not inherit them — so a caller that
	 * refits after a layout change has to restate its zoom bounds or it will
	 * blow past them.
	 */
	export type FitOptions = {
		duration?: number;
		padding?: number;
		minZoom?: number;
		maxZoom?: number;
	};

	/**
	 * One definition, used both for the <SvelteFlow> fitView attribute and for
	 * any programmatic refit. When these drifted apart the initial frame and the
	 * refit disagreed, so every page load visibly settled from one to the other.
	 */
	export const DEFAULT_FIT: FitOptions = { padding: 0.08, minZoom: 0.4, maxZoom: 1.1 };
</script>

<script lang="ts">
	// Lives inside <SvelteFlow> so it can access the flow context, and exposes
	// fitView() upward so the parent can reset pan+zoom after re-layout.
	import { useSvelteFlow } from '@xyflow/svelte';

	let { fitView = $bindable() }: { fitView?: (opts?: FitOptions) => void } = $props();

	const flow = useSvelteFlow();
	fitView = (opts) => flow.fitView({ duration: 300, ...opts });
</script>
