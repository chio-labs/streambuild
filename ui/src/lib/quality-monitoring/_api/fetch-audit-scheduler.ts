import { readApiResponse } from '$lib/api/main/response/read-api-response';
import type { AuditSchedulerPayload } from '$lib/quality-monitoring/types';

export async function fetchAuditScheduler(signal?: AbortSignal): Promise<AuditSchedulerPayload> {
	const response: Response = await fetch('/api/audit-scheduler', { signal });
	return readApiResponse<AuditSchedulerPayload>(response, 'audit scheduler');
}
