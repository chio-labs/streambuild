<script lang="ts">
	import { onMount } from 'svelte';
	import ClockIcon from '@lucide/svelte/icons/clock-3';
	import { formatAgo, formatDuration } from '$lib/domain/format';
	import { createAuditSchedulerState } from './state.svelte';
	import type { AuditScheduleState } from './types';

	const scheduler = createAuditSchedulerState();

	const STATE_LABEL: Record<AuditScheduleState, string> = {
		disabled: 'disabled for target',
		idle: 'idle',
		due: 'audits due',
		scheduled: 'scheduled',
		warming_up: 'warming up',
		running: 'running',
		blocked: 'blocked by failed build',
		backing_off: 'backing off after error'
	};

	const STATE_COLOR: Record<AuditScheduleState, string> = {
		disabled: 'var(--sb-text-faint)',
		idle: 'var(--sb-success)',
		due: 'var(--sb-warning)',
		scheduled: 'var(--sb-primary)',
		warming_up: 'var(--sb-warning)',
		running: 'var(--sb-primary)',
		blocked: 'var(--sb-error)',
		backing_off: 'var(--sb-error)'
	};

	onMount(scheduler.start);
</script>

<section class="overflow-hidden rounded-[4px] border border-border bg-[var(--sidebar-accent)]/30">
	<div class="flex items-center gap-3 border-b border-[var(--border-subtle)] px-3 py-2.5">
		<ClockIcon size={13} class="text-muted-foreground" />
		<div>
			<div class="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--sb-text-faint)]">
				Audit scheduler
			</div>
			{#if scheduler.payload}
				<div class="mt-0.5 text-xs" style:color={STATE_COLOR[scheduler.payload.health.state]}>
					{STATE_LABEL[scheduler.payload.health.state]}
				</div>
			{:else if scheduler.loading}
				<div class="text-muted-foreground mt-0.5 text-xs">reading target state…</div>
			{:else}
				<div class="mt-0.5 text-xs text-[var(--sb-error)]">scheduler state unavailable</div>
			{/if}
		</div>
		{#if scheduler.payload}
			<div class="text-muted-foreground ml-auto text-right font-mono text-[10px]">
				<div>{scheduler.payload.dueCount} due · {scheduler.payload.audits.length} scheduled</div>
				<div>
					{scheduler.payload.health.runningAuditCount
						? `${scheduler.payload.health.runningAuditCount} running`
						: `next tick in ${formatDuration(Math.ceil(scheduler.payload.health.nextTickSeconds))}`}
				</div>
			</div>
		{/if}
	</div>
	{#if scheduler.payload?.health.latestError}
		<div class="border-b border-[var(--border-subtle)] px-3 py-2 font-mono text-[10px] text-[var(--sb-error)]">
			{scheduler.payload.health.latestError}
		</div>
	{/if}
	{#if scheduler.payload && scheduler.payload.audits.length > 0}
		<div class="grid gap-px bg-[var(--border-subtle)] sm:grid-cols-2 lg:grid-cols-3">
			{#each scheduler.payload.audits.slice(0, 3) as audit (audit.name)}
				<div class="bg-background px-3 py-2">
					<div class="truncate text-xs">{audit.name}</div>
					<div class="text-muted-foreground mt-1 flex justify-between gap-2 font-mono text-[10px]">
						<span style:color={STATE_COLOR[audit.state]}>{STATE_LABEL[audit.state]}</span>
						<span>{formatAgo(audit.scheduledFor, scheduler.payload.warehouseNow ?? audit.scheduledFor)}</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}
	{#if scheduler.error && scheduler.payload}
		<div class="text-muted-foreground px-3 py-1.5 font-mono text-[9px]">refresh failed; showing last state</div>
	{/if}
</section>
