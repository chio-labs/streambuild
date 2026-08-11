import { formatAgo } from '$lib/formatting/main/format-ago';
import { formatDuration } from '$lib/formatting/main/format-duration';
import { secondsBetween } from '$lib/formatting/main/seconds-between';
import type {
	AuditScheduleItem,
	AuditScheduleState
} from '$lib/quality-monitoring/types';

export function auditScheduleLabel(item: AuditScheduleItem, warehouseNow: string): string {
	if (item.state === 'blocked') return 'blocked';
	if (item.state === 'running') return 'running';
	if (item.state === 'due') return `due ${formatAgo(item.scheduledFor, warehouseNow)}`;
	if (item.state === 'warming_up') {
		return `warms up in ${until(item.scheduledFor, warehouseNow)}`;
	}
	return `next in ${until(item.scheduledFor, warehouseNow)}`;
}

export function auditScheduleColor(state: AuditScheduleState): string {
	if (state === 'idle' || state === 'scheduled') return 'var(--sb-success)';
	if (state === 'running') return 'var(--primary)';
	if (state === 'due' || state === 'warming_up') return 'var(--sb-warning)';
	if (state === 'blocked' || state === 'backing_off') return 'var(--sb-error)';
	return 'var(--sb-text-faint)';
}

function until(instant: string, warehouseNow: string): string {
	return formatDuration(Math.max(0, secondsBetween(warehouseNow, instant)));
}
