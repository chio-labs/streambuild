import type { DeploymentDetail } from '$lib/domain/types';

export type DeploymentDetailState = {
	readonly detail: DeploymentDetail | null;
	readonly error: string | null;
	readonly loading: boolean;
	readonly requestedId: string | null;
	load: (deploymentId: string) => Promise<void>;
	cancel: () => void;
};
