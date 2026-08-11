<script lang="ts">
	// Edge type is load-bearing in StreamBuild — the single driving input is the
	// streaming spine, and a mutable reference disqualifies a replay anchor — so
	// every canvas that draws edges needs this.
	type Props = { compact?: boolean };
	let { compact = false }: Props = $props();

	/**
	 * Dash and weight carry the edge TYPE; colour and motion carry flow STATE.
	 * That is why 'driving' appears twice: a driving edge into a stalled model
	 * keeps its dash and weight but loses the hue and the animation. Without the
	 * second entry a grey dashed spine is unexplained and reads as a rendering
	 * fault.
	 */
	const items: {
		label: string;
		stroke: string;
		width: number;
		dash: string | null;
		title?: string;
	}[] = [
		{ label: 'driving', stroke: 'var(--sb-secondary)', width: 2.2, dash: '5 4' },
		{
			label: 'stalled',
			stroke: 'var(--sb-edge)',
			width: 2.2,
			dash: '5 4',
			title: 'Driving input whose model has stopped producing. Being behind is not stalled.'
		},
		{ label: 'reference', stroke: 'var(--sb-edge-dim)', width: 1.2, dash: null },
		{ label: 'view read', stroke: 'var(--sb-edge)', width: 1.9, dash: null },
		{ label: 'mutable', stroke: 'var(--sb-warning)', width: 1.5, dash: '3 3' }
	];
</script>

<div class="text-muted-foreground flex items-center gap-3 font-mono text-[10px]">
	{#each items as item (item.label)}
		<span class="flex items-center gap-1.5" title={item.title ?? item.label}>
			<svg width={compact ? 16 : 22} height="6" aria-hidden="true">
				<line
					x1="0"
					y1="3"
					x2={compact ? 16 : 22}
					y2="3"
					stroke={item.stroke}
					stroke-width={item.width}
					stroke-dasharray={item.dash}
				/>
			</svg>
			{item.label}
		</span>
	{/each}
</div>
