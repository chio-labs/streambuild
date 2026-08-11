<script lang="ts">
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import { getApp } from '$lib/api/main/project/get-app';
	import { reloadProject } from '$lib/api/main/project/reload-project';

	const app = getApp();
	const error = $derived(app.status?.error ?? null);
	const location = $derived(
		error?.path ? `${error.path}:${error.line ?? 1}:${error.column ?? 1}` : null
	);
</script>

<!--
	Compile failure stops the whole UI: there are no definitions to serve, so
	there is nothing else to show. Fix the file, hit reload.
-->
<div class="grid h-screen place-items-center px-8">
	<div class="w-full max-w-[720px]">
		<div class="flex items-center gap-2.5 pb-4">
			<TriangleAlertIcon size={18} color="var(--sb-error)" />
			<h1 class="font-display text-[18px] font-semibold">The project does not compile</h1>
		</div>
		<div
			class="rounded-[6px] border p-4"
			style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
			style:background="color-mix(in srgb, var(--sb-error) 6%, transparent)"
		>
			{#if location}
				<div class="code pb-2 text-[12px]" style:color="var(--sb-error)">{location}</div>
			{/if}
			<pre
				class="font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap">{error?.message ??
					'unknown compile error'}</pre>
		</div>
		<div class="flex items-center gap-3 pt-4">
			<button
				class="bg-primary flex items-center gap-1.5 rounded-[4px] px-3 py-1.5 font-mono text-[12px] text-white disabled:opacity-60"
				disabled={app.reloading}
				onclick={() => void reloadProject()}
			>
				<RotateIcon size={12} />
				{app.reloading ? 'compiling…' : 'reload'}
			</button>
			<span class="text-[var(--sb-text-faint)] font-mono text-[11px]">
				fix the file, then reload — the server recompiles from disk
			</span>
		</div>
	</div>
</div>
