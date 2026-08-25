const RUN_PHASE_LABELS: Record<string, string> = {
	preflight: 'check',
	preparation: 'prepare',
	teardown: 'remove',
	realization: 'create',
	stabilization: 'stabilize',
	boundary: 'boundary',
	replay: 'replay',
	audit: 'audit',
	finalization: 'finish'
};

export function labelRunPhase(phase: string | null): string {
	if (phase === null) return 'statement';
	return RUN_PHASE_LABELS[phase] ?? phase.replaceAll('_', ' ');
}
