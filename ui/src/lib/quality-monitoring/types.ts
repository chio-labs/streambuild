export type AuditScheduleState =
	| 'disabled'
	| 'idle'
	| 'due'
	| 'scheduled'
	| 'warming_up'
	| 'running'
	| 'blocked'
	| 'backing_off';

export type AuditScheduleItem = {
	name: string;
	state: AuditScheduleState;
	scheduledFor: string;
	eligibleAt: string | null;
	anchor: string | null;
	cadenceSeconds: number | null;
	warmupSeconds: number;
	lastStatus: string;
	referencedModels: string[];
	blockedReason?: 'failed_build';
};

export type AuditSchedulerHealth = {
	state: AuditScheduleState;
	consecutiveErrors: number;
	latestError: string | null;
	backoffSeconds: number;
	nextTickSeconds: number;
	lastSuccessfulTick: string | null;
	runningAuditCount: number;
};

export type AuditSchedulerPayload = {
	enabled: boolean;
	state: AuditScheduleState;
	warehouseNow: string | null;
	dueCount: number;
	audits: AuditScheduleItem[];
	health: AuditSchedulerHealth;
};

export type AuditSchedulerState = {
	readonly payload: AuditSchedulerPayload | null;
	readonly error: string | null;
	readonly loading: boolean;
	start(): () => void;
};

export type AuditSchedulerPollingResource = {
	start(): () => void;
	stop(): void;
};
