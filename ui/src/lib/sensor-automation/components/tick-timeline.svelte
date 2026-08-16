<script lang="ts">
	import { axisLabels, timestampToMs, windowFraction } from '../_helpers/timeline-scale';
	import { createTickTimeline } from '../main/_create-tick-timeline.svelte';
	import { describeTick } from '../main/describe-tick';
	import { tickTone } from '../main/tick-tone';
	import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
	import type { SensorTick, TimelineAxisLabel } from '../types';

	type Props = {
		sensorName: string;
		seedTicks: SensorTick[];
	};
	let { sensorName, seedTicks }: Props = $props();

	const timeline = createTickTimeline(() => sensorName);

	$effect(() => {
		timeline.initialize(seedTicks);
		return (): void => timeline.stop();
	});

	type PositionedTick = { tick: SensorTick; fraction: number };
	const positioned = $derived<PositionedTick[]>(
		timeline.ticks
			.map((tick) => ({
				tick,
				fraction: windowFraction(timestampToMs(tick.startedAt), timeline.startMs, timeline.endMs)
			}))
			.filter(({ fraction }) => fraction >= 0 && fraction <= 1)
	);
	const labels = $derived<TimelineAxisLabel[]>(axisLabels(timeline.startMs, timeline.endMs));

	let dragging = $state<boolean>(false);
	let lastPointerX = 0;

	function barTitle(tick: SensorTick): string {
		const detail: string = describeTick(tick);
		const suffix: string = detail === '' ? '' : ` · ${detail}`;
		return `${tick.status} · attempt ${tick.attempt} · ${formatTimestamp(tick.startedAt)}${suffix}`;
	}

	function onWheel(event: WheelEvent): void {
		event.preventDefault();
		const strip: HTMLElement = event.currentTarget as HTMLElement;
		timeline.zoomAt(event.offsetX / strip.clientWidth, event.deltaY);
	}

	function onPointerDown(event: PointerEvent): void {
		dragging = true;
		lastPointerX = event.clientX;
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
	}

	function onPointerMove(event: PointerEvent): void {
		if (!dragging) return;
		const strip: HTMLElement = event.currentTarget as HTMLElement;
		timeline.panBy(-(event.clientX - lastPointerX) / strip.clientWidth);
		lastPointerX = event.clientX;
	}

	function onPointerUp(): void {
		dragging = false;
	}
</script>

<div class="pt-2">
	<div
		class="relative h-[26px] touch-none select-none overflow-hidden rounded-[3px] border border-[var(--border-subtle)]"
		class:cursor-grab={!dragging}
		class:cursor-grabbing={dragging}
		data-testid="tick-timeline"
		role="application"
		aria-label="Tick timeline; scroll to zoom, drag to pan, double-click to reset"
		style:opacity={timeline.loading ? 0.55 : 1}
		onwheel={onWheel}
		onpointerdown={onPointerDown}
		onpointermove={onPointerMove}
		onpointerup={onPointerUp}
		onpointercancel={onPointerUp}
		ondblclick={() => timeline.reset()}
	>
		{#each positioned as { tick, fraction } (tick.tickId)}
			<span
				class="absolute top-[4px] h-[16px] w-[6px] -translate-x-1/2 rounded-[1.5px]"
				style:left={`${fraction * 100}%`}
				style:background={tickTone(tick.status)}
				title={barTitle(tick)}
			></span>
		{/each}
		{#if positioned.length === 0 && !timeline.loading}
			<span
				class="text-[var(--sb-text-faint)] absolute inset-0 grid place-items-center font-mono text-[10px]"
			>
				no ticks in window
			</span>
		{/if}
	</div>
	<div class="relative h-[14px]">
		{#each labels as label (label.fraction)}
			<span
				class="text-[var(--sb-text-faint)] absolute top-[2px] -translate-x-1/2 font-mono text-[9.5px]"
				style:left={`${label.fraction * 100}%`}
			>
				{label.text}
			</span>
		{/each}
	</div>
	<div class="text-[var(--sb-text-faint)] flex justify-between pt-0.5 font-mono text-[10px]">
		<span>scroll to zoom · drag to pan · double-click to reset</span>
		<span>
			{#if timeline.error !== null}
				<span style:color="var(--sb-error)">{timeline.error}</span>
			{:else}
				{positioned.length}
				{positioned.length === 1 ? 'tick' : 'ticks'} in window
			{/if}
		</span>
	</div>
</div>
