const TICK_TONES: Record<string, string> = {
	succeeded: 'var(--sb-success)',
	skipped: 'var(--sb-warning)',
	failed: 'var(--sb-error)',
	dead_lettered: 'var(--sb-error)',
	started: 'var(--sb-warning)'
};

export function tickTone(status: string): string {
	return TICK_TONES[status] ?? 'var(--sb-text-faint)';
}
