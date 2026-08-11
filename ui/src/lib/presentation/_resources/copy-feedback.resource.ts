export type CopyFeedbackResource = {
	schedule(): void;
	stop(): void;
};

export function createCopyFeedbackResource(reset: () => void): CopyFeedbackResource {
	let timer: ReturnType<typeof setTimeout> | null = null;

	return {
		schedule(): void {
			timer = setTimeout(() => {
				timer = null;
				reset();
			}, 1_200);
		},
		stop(): void {
			if (timer !== null) clearTimeout(timer);
			timer = null;
		}
	};
}
