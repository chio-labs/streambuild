export const RUN_OUTCOME_COLORS: Record<string, string> = {
	running: 'var(--sb-secondary)',
	succeeded: 'var(--sb-success)',
	failed: 'var(--sb-error)',
	cancelled: 'var(--sb-warning)',
	unresponsive: 'var(--sb-warning)',
	presumed_failed: 'var(--sb-warning)'
};

export const RUN_DETAIL_POLL_MS: number = 1_200;
export const RUN_SNAPSHOT_MAX_AGE_MS: number = 10_000;
