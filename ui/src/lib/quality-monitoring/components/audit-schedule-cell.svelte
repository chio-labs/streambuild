<script lang="ts">
	import { auditScheduleColor, auditScheduleLabel } from '$lib/quality-monitoring/_helpers/audit-schedule';
	import type {
		AuditScheduleItem,
		AuditSchedulerPayload
	} from '$lib/quality-monitoring/types';

	let {
		scheduled,
		schedule,
		payload,
		error
	}: {
		scheduled: boolean;
		schedule: AuditScheduleItem | undefined;
		payload: AuditSchedulerPayload | null;
		error: string | null;
	} = $props();

	function missingScheduleLabel(): string {
		if (!payload) return error ? 'schedule unavailable' : 'loading schedule…';
		if (!payload.enabled) return 'scheduler disabled';
		if (payload.health.state === 'running') return 'scheduler running';
		if (payload.health.state === 'backing_off') return 'retry pending';
		return 'schedule unavailable';
	}
</script>

<span
	class="w-[108px] shrink-0 truncate text-right font-mono text-[10.5px] sm:w-[138px]"
	style:color={schedule ? auditScheduleColor(schedule.state) : 'var(--sb-text-faint)'}
	title={schedule?.missingRelations.length
		? `Missing relations: ${schedule.missingRelations.join(', ')}`
		: (schedule?.scheduledFor ?? undefined)}
>
	{#if !scheduled}
		manual
	{:else if schedule && payload?.warehouseNow}
		{auditScheduleLabel(schedule, payload.warehouseNow)}
	{:else}
		{missingScheduleLabel()}
	{/if}
</span>
