<script lang="ts">
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import FactRow from '$lib/components/fact-row.svelte';
	import { app, reloadProject } from '$lib/api/store.svelte';
	import { getProject } from '$lib/api';

	const project = getProject();
	const status = $derived(app.status);
	const timingEntries = $derived(Object.entries(status?.timings ?? {}));
</script>

<AppTopbar title="Status" />

<div class="min-h-0 flex-1 overflow-y-auto px-[18px] py-4">
	<div class="grid max-w-[880px] gap-4" style:grid-template-columns="minmax(0,1fr) minmax(0,1fr)">
		<div class="rounded-[4px] border border-border p-4">
			<div class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]">
				Project compile
			</div>
			<div class="flex items-center gap-2 pb-3">
				<span
					class="h-[8px] w-[8px] rounded-full"
					style:background={status?.state === 'ok' ? 'var(--sb-success)' : 'var(--sb-error)'}
				></span>
				<span class="font-mono text-[13px]">{status?.state ?? 'unknown'}</span>
				<button
					class="text-muted-foreground hover:text-foreground ml-auto flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px] disabled:opacity-60"
					disabled={app.reloading}
					onclick={() => void reloadProject()}
				>
					<RotateIcon size={11} />
					{app.reloading ? 'compiling…' : 'reload'}
				</button>
			</div>
			<FactRow label="compiled at" value={status?.compiledAt ?? '—'} />
			<FactRow label="version" value={status?.versionKey ?? '—'} />
			{#each timingEntries as [name, ms] (name)}
				<FactRow label={name.replace('Ms', '')} value={`${ms} ms`} />
			{/each}
		</div>

		<div class="rounded-[4px] border border-border p-4">
			<div class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]">
				Warehouse
			</div>
			<div class="flex items-center gap-2 pb-3">
				<span
					class="h-[8px] w-[8px] rounded-full"
					style:background={status?.warehouseConnected ? 'var(--sb-success)' : 'var(--sb-error)'}
				></span>
				<span class="font-mono text-[13px]"
					>{status?.warehouseConnected ? 'connected' : 'unreachable'}</span
				>
			</div>
			<FactRow label="adapter" value={project.adapter} />
			<FactRow label="database" value={project.database} />
			<FactRow label="target" value={project.target} />
			<FactRow label="snapshot" value={project.capturedAt} />
			{#if status?.warehouseError}
				<div class="pt-2 font-mono text-[11px]" style:color="var(--sb-error)">
					{status.warehouseError}
				</div>
			{/if}
		</div>

		<div class="rounded-[4px] border border-border p-4" style:grid-column="1 / -1">
			<div class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]">
				Definitions
			</div>
			<div class="flex flex-wrap gap-x-6 gap-y-1 font-mono text-[12px]">
				<span>{project.pipelines.length} pipelines</span>
				<span>{project.models.length} models</span>
				<span>{project.sources.length} sources</span>
				<span>{project.audits.length} audits</span>
				<span>{project.tests.length} tests</span>
				<span>{project.macros.length} macros</span>
			</div>
		</div>
	</div>
</div>
