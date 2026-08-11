import type { Project } from '$lib/domain/types';

export type KafkaLagRetryResource = {
	schedule(project: Project | null): void;
	reset(): void;
};

export function createKafkaLagRetryResource(
	refresh: () => Promise<void>
): KafkaLagRetryResource {
	const delays: readonly number[] = [1_000, 4_000, 10_000];
	let timer: ReturnType<typeof setTimeout> | null = null;
	let attempt: number = 0;

	return {
		schedule(project: Project | null): void {
			if (
				timer !== null ||
				attempt >= delays.length ||
				project === null ||
				!project.sources.some(
					(source) => source.kind === 'kafka' && source.live.kafkaLagMessages === null
				)
			) {
				return;
			}
			const delay: number = delays[attempt];
			attempt += 1;
			timer = setTimeout(() => {
				timer = null;
				if (!document.hidden) void refresh();
			}, delay);
		},
		reset(): void {
			if (timer !== null) clearTimeout(timer);
			timer = null;
			attempt = 0;
		}
	};
}
