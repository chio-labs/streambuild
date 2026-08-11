<script lang="ts">
	type Props = {
		values: number[];
		width?: number;
		height?: number;
		colour?: string;
		/** Filled area under the line reads better at small sizes for throughput. */
		fill?: boolean;
	};
	let {
		values,
		width = 148,
		height = 26,
		colour = 'var(--sb-secondary)',
		fill = true
	}: Props = $props();

	const max = $derived(Math.max(...values, 1));
	const step = $derived(values.length > 1 ? width / (values.length - 1) : width);

	const points = $derived(
		values
			.map((value, index) => {
				const x: number = index * step;
				const y: number = height - (value / max) * (height - 2) - 1;
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ')
	);

	const areaPoints = $derived(`0,${height} ${points} ${width},${height}`);
</script>

<svg {width} {height} viewBox="0 0 {width} {height}" class="block" aria-hidden="true">
	{#if fill}
		<polygon {...{ points: areaPoints }} fill={colour} opacity="0.14" />
	{/if}
	<polyline
		{...{ points }}
		fill="none"
		stroke={colour}
		stroke-width="1.4"
		stroke-linejoin="round"
		stroke-linecap="round"
	/>
</svg>
