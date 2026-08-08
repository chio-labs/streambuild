import { readApiResponse } from '$lib/api';
import type { AuditSchedulerPayload } from '../types';

export async function fetchAuditScheduler(signal?: AbortSignal): Promise<AuditSchedulerPayload> {
	const response = await fetch('/api/audit-scheduler', { signal });
	return readApiResponse<AuditSchedulerPayload>(response, 'audit scheduler');
}
