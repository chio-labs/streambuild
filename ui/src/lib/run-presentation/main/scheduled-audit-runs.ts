import type { RunRecord } from '$lib/api/types';

export function scheduledAuditRuns(runs: RunRecord[]): RunRecord[] {
	return runs.filter((run) => run.command === 'audit' && run.mode === 'scheduled');
}
