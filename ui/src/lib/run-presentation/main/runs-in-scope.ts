import type { RunRecord } from '$lib/api/types';

export type RunScope = 'builds' | 'other' | 'all';

export function runsInScope(runs: RunRecord[], scope: RunScope): RunRecord[] {
	if (scope === 'builds') return runs.filter((run) => run.command === 'build');
	if (scope === 'other') {
		return runs.filter(
			(run) => run.command !== 'build' && !(run.command === 'audit' && run.mode === 'scheduled')
		);
	}
	return runs;
}
