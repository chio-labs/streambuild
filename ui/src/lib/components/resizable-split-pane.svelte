<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import { clamp } from '$lib/domain/format';

	type Props = {
		main: Snippet;
		sidebar: Snippet;
		storageKey: string;
		initialWidth?: number;
		minWidth?: number;
		maxWidth?: number;
		minMainWidth?: number;
	};

	let {
		main,
		sidebar,
		storageKey,
		initialWidth = 320,
		minWidth = 260,
		maxWidth = 560,
		minMainWidth = 480
	}: Props = $props();

	let container: HTMLDivElement;
	let sidebarWidth: number = $derived(initialWidth);
	let dragging = $state<boolean>(false);

	const HANDLE_WIDTH: number = 12;
	const KEYBOARD_STEP: number = 16;

	onMount(() => {
		try {
			const storedWidth: number = Number(localStorage.getItem(storageKey));
			if (Number.isFinite(storedWidth) && storedWidth > 0) setWidth(storedWidth, false);
		} catch {
			// A blocked preference store must not make the detail page unusable.
		}
	});

	function effectiveMaxWidth(): number {
		if (!container) return maxWidth;
		return Math.max(
			minWidth,
			Math.min(maxWidth, container.getBoundingClientRect().width - minMainWidth - HANDLE_WIDTH)
		);
	}

	function setWidth(width: number, persist: boolean = true): void {
		sidebarWidth = clamp(width, minWidth, effectiveMaxWidth());
		if (!persist) return;
		try {
			localStorage.setItem(storageKey, String(sidebarWidth));
		} catch {
			// Preferences are optional and never block interaction.
		}
	}

	function startResize(event: PointerEvent): void {
		if (event.button !== 0) return;
		dragging = true;
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
	}

	function resize(event: PointerEvent): void {
		if (!dragging) return;
		const bounds: DOMRect = container.getBoundingClientRect();
		setWidth(bounds.right - event.clientX, false);
	}

	function finishResize(event: PointerEvent): void {
		if (!dragging) return;
		dragging = false;
		const handle: HTMLElement = event.currentTarget as HTMLElement;
		if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
		setWidth(sidebarWidth);
	}

	function resizeWithKeyboard(event: KeyboardEvent): void {
		if (event.key === 'ArrowLeft') setWidth(sidebarWidth + KEYBOARD_STEP);
		else if (event.key === 'ArrowRight') setWidth(sidebarWidth - KEYBOARD_STEP);
		else if (event.key === 'Home') setWidth(minWidth);
		else if (event.key === 'End') setWidth(effectiveMaxWidth());
		else return;
		event.preventDefault();
	}
</script>

<svelte:window onresize={() => setWidth(sidebarWidth, false)} />

<div
	bind:this={container}
	class="resizable-split grid grid-cols-1 gap-5 p-[18px] xl:gap-0 {dragging ? 'select-none' : ''}"
	style:--sidebar-width="{sidebarWidth}px"
>
	<div class="min-w-0">{@render main()}</div>
	<button
		type="button"
		class="group hidden cursor-col-resize items-stretch justify-center px-[5px] outline-none xl:flex"
		aria-label="Resize source details sidebar"
		title="Drag to resize; double-click to reset"
		onpointerdown={startResize}
		onpointermove={resize}
		onpointerup={finishResize}
		onpointercancel={finishResize}
		onkeydown={resizeWithKeyboard}
		ondblclick={() => setWidth(initialWidth)}
	>
		<span
			class="w-px bg-border transition-colors group-hover:bg-[var(--primary)] group-focus-visible:bg-[var(--primary)]"
		></span>
	</button>
	<div class="min-w-0">{@render sidebar()}</div>
</div>

<style>
	@media (min-width: 1280px) {
		.resizable-split {
			grid-template-columns: minmax(0, 1fr) 12px var(--sidebar-width);
		}
	}
</style>
