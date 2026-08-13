export type SensorTick = {
	tickId: string;
	sensorName: string;
	definitionFingerprint: string;
	kind: string;
	eventId: string | null;
	eventKind: string | null;
	attempt: number;
	status: string;
	startedAt: string;
	completedAt: string | null;
	errorMessage: string | null;
	skipReason: string | null;
	cursor: string | null;
};

export type SensorRetryPolicy = {
	maxAttempts: number;
	backoffSeconds: number;
};

export type SensorSummary = {
	name: string;
	kind: string;
	description: string | null;
	file: string;
	fingerprint: string;
	defaultStatus: string;
	effectiveStatus: string;
	override: string | null;
	retryPolicy: SensorRetryPolicy;
	timeoutSeconds: number;
	lastTick: SensorTick | null;
	eventType?: string;
	targets?: string[] | null;
	triggers?: string[] | null;
	minimumIntervalSeconds?: number;
};

export type SensorSchedulerHealth = {
	state: string;
	consecutiveErrors: number;
	latestError: string | null;
	backoffSeconds: number;
	nextTickSeconds: number;
	lastSuccessfulTick: string | null;
	lastEvaluatedCount: number | null;
	leaseHeld: boolean | null;
};

export type SensorsPayload = {
	sensors: SensorSummary[];
	deadLetterCount: number;
	health: SensorSchedulerHealth;
};

export type SensorTicksPayload = {
	sensorName: string;
	ticks: SensorTick[];
};

export type DeadLettersPayload = {
	deadLetters: SensorTick[];
};

export type SensorStatusResult = {
	sensorName: string;
	status: string;
};

export type DeadLetterActionResult = {
	sensorName: string;
	eventId: string;
	status: string;
};

export type SensorsState = {
	readonly payload: SensorsPayload | null;
	readonly deadLetters: SensorTick[];
	readonly selectedSensor: string | null;
	readonly ticks: SensorTick[];
	readonly loading: boolean;
	readonly error: string | null;
	readonly actionError: string | null;
	readonly busy: boolean;
	start: () => () => void;
	selectSensor: (name: string | null) => Promise<void>;
	setStatus: (name: string, status: string) => Promise<void>;
	retryDeadLetter: (sensorName: string, eventId: string) => Promise<void>;
	skipDeadLetter: (sensorName: string, eventId: string, reason: string) => Promise<void>;
};

export type SensorsPollingResource = {
	start: () => () => void;
	stop: () => void;
};
