<script lang="ts">
	import type { RunEventFeed } from '$lib/api/types';
	import { formatBytes } from '$lib/formatting/main/format-bytes';
	import { formatCompact } from '$lib/formatting/main/format-compact';
	import { formatDuration } from '$lib/formatting/main/format-duration';
	import { formatRate } from '$lib/formatting/main/format-rate';
	import { buildStatementProgressPresentation } from '$lib/run-presentation/main/build-statement-progress-presentation';
	import type { StatementProgressPresentation } from '$lib/run-presentation/types';
	type StatementProgress = NonNullable<RunEventFeed['statementProgress']>;

	type Props = {
		progress: StatementProgress;
		label: string;
		totalStatements: number | null;
		workerSignalAgeSeconds: number | null;
	};

	const { progress, label, totalStatements, workerSignalAgeSeconds }: Props = $props();
	const presentation = $derived<StatementProgressPresentation>(
		buildStatementProgressPresentation(progress, totalStatements)
	);
	const settings = $derived(Object.entries(progress.settings ?? {}));
</script>

<section class="mx-[18px] mt-3 rounded-[4px] border border-border bg-[var(--sb-surface-low)]" aria-label="Active statement progress">
	<div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--border-subtle)] px-3 py-2">
		<span class="sb-tag code">{progress.phase ?? 'statement'}</span>
		<strong class="code min-w-0 flex-1 truncate text-[12px]" title={label}>
			{presentation.position} {label}
		</strong>
		<span class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">
			{presentation.pendingStatements ?? 'unknown'} pending
		</span>
	</div>

	{#if progress.found}
		<div class="grid grid-cols-2 gap-px bg-[var(--border-subtle)] sm:grid-cols-3 lg:grid-cols-6">
			<div class="bg-background px-3 py-2">
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px] uppercase">elapsed</div>
				<div class="code pt-0.5 text-[11.5px]">{formatDuration(progress.elapsedSeconds ?? 0)}</div>
			</div>
			<div class="bg-background px-3 py-2">
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px] uppercase">rows read</div>
				<div class="code pt-0.5 text-[11.5px]">{formatCompact(progress.readRows ?? 0)}</div>
			</div>
			<div class="bg-background px-3 py-2">
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px] uppercase">bytes read</div>
				<div class="code pt-0.5 text-[11.5px]">{formatBytes(progress.readBytes ?? 0)}</div>
			</div>
			<div class="bg-background px-3 py-2">
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px] uppercase">avg throughput</div>
				<div class="code pt-0.5 text-[11.5px]">{formatRate(progress.readRowsPerSecond ?? 0)}</div>
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px]">{formatBytes(progress.readBytesPerSecond ?? 0)}/s</div>
			</div>
			<div class="bg-background px-3 py-2">
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px] uppercase">memory</div>
				<div class="code pt-0.5 text-[11.5px]">{formatBytes(progress.memoryUsageBytes ?? 0)}</div>
			</div>
			<div class="bg-background px-3 py-2">
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px] uppercase">telemetry</div>
				<div class="pt-0.5 font-mono text-[10.5px]" style:color="var(--sb-success)">query active</div>
				<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px]">worker {workerSignalAgeSeconds ?? 0}s ago</div>
			</div>
		</div>

		<div class="px-3 py-2">
			<div class="h-[4px] w-full overflow-hidden rounded-full bg-[var(--sb-inset)]">
				{#if presentation.percentage !== null}
					<div class="h-full rounded-full bg-[var(--sb-secondary)] transition-all" style:width="{presentation.percentage}%"></div>
				{:else}
					<div class="h-full w-1/3 animate-pulse rounded-full bg-[var(--sb-secondary)]"></div>
				{/if}
			</div>
			<div class="text-[var(--sb-text-faint)] flex justify-between pt-1 font-mono text-[9.5px]">
				<span>{presentation.percentage === null ? 'progress denominator unavailable' : `approximately ${presentation.percentage.toFixed(1)}%`}</span>
				{#if presentation.etaSeconds !== null}<span>ETA {formatDuration(presentation.etaSeconds)}</span>{/if}
			</div>
		</div>
	{:else}
		<div class="px-3 py-2 font-mono text-[10.5px]" style:color="var(--sb-warning)">
			Query telemetry is unavailable or stale. Worker heartbeat: {workerSignalAgeSeconds ?? 0}s ago.
		</div>
	{/if}

	{#if settings.length > 0}
		<div class="flex flex-wrap gap-1.5 border-t border-[var(--border-subtle)] px-3 py-2">
			<span class="text-[var(--sb-text-faint)] pr-1 font-mono text-[9.5px] uppercase">effective settings</span>
			{#each settings as [name, value] (name)}
				<span class="sb-tag code">{name}={value}</span>
			{/each}
		</div>
	{/if}
</section>
