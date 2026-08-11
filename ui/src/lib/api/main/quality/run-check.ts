import { requestCheckRun } from '$lib/api/_api/quality';
import type { CheckRunResult } from '$lib/api/types';

export async function runCheck(
	kind: 'audit' | 'test',
	name: string
): Promise<CheckRunResult> {
	return requestCheckRun(kind, name);
}
