<script lang="ts">
	import { updated } from '$app/state';

	function reload(): void {
		window.location.reload();
	}
</script>

{#if updated.current}
	<div
		class="fixed right-4 bottom-4 z-[100] flex items-center gap-3 rounded-[5px] border border-border bg-popover px-3 py-2 text-popover-foreground shadow-xl"
		role="status"
		aria-live="polite"
	>
		<span class="font-mono text-[11px]">A new version is available.</span>
		<button
			type="button"
			class="rounded-[3px] border border-[var(--primary)] bg-[var(--primary)] px-2 py-1 font-mono text-[10.5px] text-[var(--primary-foreground)] hover:opacity-90"
			onclick={reload}
		>
			Reload
		</button>
	</div>
{/if}
