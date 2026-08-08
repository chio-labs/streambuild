/** Wire types for the broker topic inventory. */

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
