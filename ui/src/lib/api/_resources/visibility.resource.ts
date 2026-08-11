export type VisibilityResource = {
	start(): void;
	stop(): void;
};

export function createVisibilityResource(refresh: () => Promise<void>): VisibilityResource {
	let started: boolean = false;
	const handleVisibilityChange: () => void = (): void => {
		if (!document.hidden) void refresh();
	};

	return {
		start(): void {
			if (started || typeof document === 'undefined') return;
			started = true;
			document.addEventListener('visibilitychange', handleVisibilityChange);
		},
		stop(): void {
			if (!started || typeof document === 'undefined') return;
			document.removeEventListener('visibilitychange', handleVisibilityChange);
			started = false;
		}
	};
}
