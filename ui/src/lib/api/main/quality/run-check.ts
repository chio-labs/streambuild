import { requestAuditBatchRun, requestCheckRun } from '$lib/api/_api/quality';
import type { CheckRunResult } from '$lib/api/types';

export async function runCheck(
	request:
		| { kind: 'audit' | 'test'; name: string }
		| { kind: 'audits'; names: string[] }
): Promise<CheckRunResult | (CheckRunResult & { name: string })[]> {
	if (request.kind === 'audits') return requestAuditBatchRun(request.names);
	return requestCheckRun(request.kind, request.name);
}
