<script lang="ts">
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import type { ServerStatus } from '$lib/api/types';
	import { formatClock } from '$lib/formatting/main/format-clock';
	import ErrorView from '$lib/presentation/components/error-view.svelte';

	type Props = {
		status: ServerStatus;
		refreshing: boolean;
		onretry(): void;
	};
	let { status, refreshing, onretry }: Props = $props();
	const lastAttempt = $derived(formatClock(status.warehouseLastAttemptAt));
	const nextAttempt = $derived(formatClock(status.warehouseNextAttemptAt));
	const error = $derived(status.warehouseError ?? 'The connection attempt has not completed.');
</script>

<div
	class="flex shrink-0 items-start gap-3 border-b px-[18px] py-3 font-mono text-[11px]"
	style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
	style:background="color-mix(in srgb, var(--sb-error) 10%, var(--background))"
>
	<TriangleAlertIcon size={15} class="mt-px shrink-0" color="var(--sb-error)" />
	<div class="min-w-0 flex-1">
		<div class="font-semibold" style:color="var(--sb-error)">Warehouse unavailable.</div>
		<div class="mt-0.5 text-foreground">
			Planning and builds are paused because current warehouse state cannot be read.
		</div>
		<div class="text-muted-foreground mt-1">
			{#if status.warehouseNextAttemptAt}
				Next scheduled connection check: {nextAttempt}. Retry delays are capped at 30 seconds;
				connection attempts can take longer.
			{:else if status.warehouseState === 'retrying'}
				StreamBuild will keep trying in the background. Retry delays are capped at 30 seconds;
				connection attempts can take longer.
			{:else}
				Automatic reconnection is unavailable for this server configuration.
			{/if}
		</div>
		<div class="mt-2 flex flex-wrap items-center gap-3">
			<button
				class="hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 text-muted-foreground disabled:opacity-60"
				disabled={refreshing}
				onclick={onretry}
			>
				<span class:animate-spin={refreshing}><RefreshCwIcon size={11} /></span>
				{refreshing ? 'Trying…' : 'Retry now'}
			</button>
			<details class="min-w-0">
				<summary class="cursor-pointer text-muted-foreground hover:text-foreground">
					Technical details
				</summary>
				<div class="mt-2 grid gap-1 rounded-[4px] border border-border bg-[var(--sb-inset)] p-2">
					<div><span class="text-muted-foreground">Last attempt:</span> {lastAttempt}</div>
					<div><span class="text-muted-foreground">Next attempt:</span> {nextAttempt}</div>
					<div class="mt-1"><ErrorView text={error} maxHeight="9rem" /></div>
				</div>
			</details>
		</div>
	</div>
</div>
