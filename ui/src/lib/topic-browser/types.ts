export type TopicSourceLink = {
	name: string;
	relationName: string;
};

export type TopicItem = {
	name: string;
	brokerList: string;
	partitions: number | null;
	replicationFactor: number | null;
	internal: boolean;
	sources: TopicSourceLink[];
	lagMessages: number | null;
	retainedRows: number | null;
	retainedBytes: number | null;
};

export type TopicsPayload = {
	available: boolean;
	reason: string | null;
	pendingBrokers: string[];
	topics: TopicItem[];
};

export type TopicBrowserState = {
	readonly payload: TopicsPayload | null;
	readonly error: string | null;
	readonly loading: boolean;
	readonly updatedAt: number | null;
	refresh(): Promise<boolean>;
	start(): () => void;
	stop(): void;
	ensureLoaded(): Promise<void>;
};

export type TopicPollingResource = {
	start(): () => void;
	stop(): void;
};
