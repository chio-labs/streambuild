<script module lang="ts">
	export type OverlayLabel = {
		groupKey: string;
		label: string;
		sublabel: string | null;
		modelCount: number;
		/** Canvas-space top-left of the group. */
		x: number;
		y: number;
		width: number;
		collapsible: boolean;
	};
</script>

<script lang="ts">
	import { useStore } from '@xyflow/svelte';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';

	type Props = {
		labels: OverlayLabel[];
		ontoggle: (groupKey: string) => void;
	};
	let { labels, ontoggle }: Props = $props();

	/**
	 * Group labels are drawn OUTSIDE the canvas transform, at constant screen size.
	 *
	 * The previous approach counter-scaled the label inside the canvas
	 * (`scale(1/zoom)`), which keeps its screen size constant but makes it occupy
	 * more and more CANVAS space as you zoom out — so it burst out of the band it
	 * was meant to sit in and collided with the nodes below. Screen-space is the
	 * only version that is stable at every zoom.
	 */
	const store = useStore();
	const viewport = $derived(store.viewport);

	/** Hide a label once its group is too small on screen to be worth naming. */
	const MIN_SCREEN_WIDTH = 90;

	const placed = $derived(
		labels
			.map((item) => {
				const screenX: number = item.x * viewport.zoom + viewport.x;
				const screenY: number = item.y * viewport.zoom + viewport.y;
				return {
					item,
					screenWidth: item.width * viewport.zoom,
					// Clamp to the left edge so the label stays visible when a wide group
					// is panned partly off-screen — the same idea as a sticky row header.
					left: Math.max(screenX, 6),
					top: screenY
				};
			})
			.filter((entry) => entry.screenWidth >= MIN_SCREEN_WIDTH)
	);
</script>

<div class="pointer-events-none absolute inset-0 overflow-hidden" style:z-index="6">
	{#each placed as entry (entry.item.groupKey)}
		<div
			class="absolute flex items-center gap-1.5 whitespace-nowrap rounded-[5px]"
			style:left="{entry.left}px"
			style:top="{entry.top}px"
			style:max-width="{Math.max(entry.screenWidth, 0)}px"
			style:height="24px"
			style:padding="0 8px"
			style:background="var(--sb-group-header)"
			style:border="1px solid var(--sb-group-border)"
		>
			{#if entry.item.collapsible}
				<button
					class="text-muted-foreground hover:text-foreground pointer-events-auto grid h-[16px] w-[16px] shrink-0 place-items-center rounded-[3px]"
					aria-label="Collapse pipeline"
					onclick={(event) => {
						event.stopPropagation();
						ontoggle(entry.item.groupKey);
					}}
				>
					<ChevronDownIcon size={13} />
				</button>
			{/if}
			<span class="truncate font-mono text-[12px] font-medium leading-none"
				>{entry.item.label}</span
			>
			{#if entry.item.sublabel}
				<span class="text-[var(--sb-text-faint)] font-mono text-[10px] leading-none"
					>{entry.item.sublabel}</span
				>
			{/if}
			<span class="text-[var(--sb-text-faint)] font-mono text-[10px] leading-none"
				>· {entry.item.modelCount}</span
			>
		</div>
	{/each}
</div>
