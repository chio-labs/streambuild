<script lang="ts">
	import { clamp } from '$lib/domain/format';

	export type TrackBand = {
		from: string;
		to: string;
		colour: string;
		/** Diagonal hatch = unavailable / not-replayed region. */
		hatch?: boolean;
		opacity?: number;
		label?: string;
	};

	type Props = {
		/** The full time domain the track represents. */
		domainFrom: string;
		domainTo: string;
		bands: TrackBand[];
		/** Optional vertical marker, e.g. a chosen --start-time. */
		markerAt?: string | null;
		markerLabel?: string | null;
		height?: number;
	};
	let {
		domainFrom,
		domainTo,
		bands,
		markerAt = null,
		markerLabel = null,
		height = 20
	}: Props = $props();

	const domainStart = $derived(new Date(domainFrom).getTime());
	const domainEnd = $derived(new Date(domainTo).getTime());
	const span = $derived(Math.max(domainEnd - domainStart, 1));

	function fraction(instant: string): number {
		return clamp((new Date(instant).getTime() - domainStart) / span, 0, 1);
	}

	const geometry = $derived(
		bands.map((band) => {
			const left: number = fraction(band.from);
			const right: number = fraction(band.to);
			return { band, left: left * 100, width: Math.max((right - left) * 100, 0.4) };
		})
	);

	const markerFraction = $derived(markerAt ? fraction(markerAt) * 100 : null);
</script>

<div class="sb-track" style:height="{height}px">
	{#each geometry as item (item.band.from + item.band.to + item.band.colour)}
		<div
			class="sb-track-fill {item.band.hatch ? 'sb-track-hatch' : ''}"
			style:left="{item.left}%"
			style:width="{item.width}%"
			style:background={item.band.hatch ? undefined : item.band.colour}
			style:opacity={item.band.opacity ?? 1}
			title={item.band.label}
		></div>
	{/each}
	{#if markerFraction !== null}
		<div
			class="absolute bottom-0 top-0 w-[2px]"
			style:left="{markerFraction}%"
			style:background="var(--primary)"
			title={markerLabel ?? undefined}
		></div>
	{/if}
</div>
