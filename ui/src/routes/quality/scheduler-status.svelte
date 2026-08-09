<script lang="ts">
	import ClockIcon from '@lucide/svelte/icons/clock-3';
	import { formatDuration } from '$lib/domain/format';
	import type { AuditSchedulerPayload } from './types';
	import { auditScheduleColor } from './utils';

	let {
		payload,
		loading,
		error
	}: { payload: AuditSchedulerPayload | null; loading: boolean; error: string | null } = $props();

	const display = $derived.by(() => {
		if (!payload) return null;
		if (!payload.enabled) return { label: 'Disabled for this target', state: 'disabled' as const, detail: null };
		if (payload.state === 'blocked') {
			return {
				label: 'Paused after the latest failed direct build',
				state: 'blocked' as const,
				detail: 'A successful direct build will resume scheduled audits.'
			};
		}
		if (payload.health.state === 'backing_off') {
			return {
				label: 'Retrying after a scheduler error',
				state: 'backing_off' as const,
				detail: payload.health.latestError
			};
		}
		if (payload.health.state === 'blocked' && payload.health.latestError) {
			return {
				label: 'Standing by',
				state: 'scheduled' as const,
				detail: payload.health.latestError
			};
		}
		if (payload.health.state === 'blocked') {
			return {
				label: 'Paused while a build is running',
				state: 'blocked' as const,
				detail: 'Scheduled audits resume when the active build finishes.'
			};
		}
		if (payload.health.runningAuditCount > 0) {
			return {
				label: `${payload.health.runningAuditCount} audit${payload.health.runningAuditCount === 1 ? '' : 's'} running`,
				state: 'running' as const,
				detail: null
			};
		}
		if (payload.dueCount > 0) {
			return {
				label: `${payload.dueCount} audit${payload.dueCount === 1 ? '' : 's'} due`,
				state: 'due' as const,
				detail: null
			};
		}
		return { label: 'Active', state: 'idle' as const, detail: null };
	});
</script>

<section class="rounded-[4px] border border-border bg-[var(--sidebar-accent)]/20 px-3 py-2.5">
	<div class="flex min-h-8 items-center gap-3">
		<ClockIcon size={13} class="text-muted-foreground" />
		<div class="min-w-0">
			<div class="flex items-baseline gap-2">
				<span class="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--sb-text-faint)]">
					Audit scheduler
				</span>
				{#if display}
					<span class="text-xs" style:color={auditScheduleColor(display.state)}>{display.label}</span>
				{:else if loading}
					<span class="text-muted-foreground text-xs">Reading target state…</span>
				{:else}
					<span class="text-xs text-[var(--sb-error)]">Unavailable</span>
				{/if}
			</div>
			{#if display?.detail}
				<div class="text-muted-foreground mt-0.5 truncate font-mono text-[10px]" title={display.detail}>
					{display.detail}
				</div>
			{:else if error && payload}
				<div class="text-muted-foreground mt-0.5 font-mono text-[10px]">Refresh failed; showing last state</div>
			{/if}
		</div>
		{#if payload}
			<div class="text-muted-foreground ml-auto text-right font-mono text-[10px]">
				{#if payload.audits.length > 0}
					<div>{payload.audits.length} scheduled · {payload.dueCount} due</div>
				{/if}
				<div>checks again in {formatDuration(Math.ceil(payload.health.nextTickSeconds))}</div>
			</div>
		{/if}
	</div>
</section>
