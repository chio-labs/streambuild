import { createAuditSchedulerState as createState } from '$lib/quality-monitoring/_state/audit-scheduler.state.svelte';
import type { AuditSchedulerState } from '$lib/quality-monitoring/types';

export function createAuditSchedulerState(): AuditSchedulerState {
	return createState();
}
