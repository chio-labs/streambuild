import { requestPlan } from '$lib/api/_api/plan';
import { planFromServer } from '$lib/api/_helpers/mapping';
import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';
import type { Project } from '$lib/domain/types';
import type { Plan } from '$lib/planning/types';

type FetchPlanOptions = {
	selectors: string[];
	changed?: boolean;
	includeMissingUpstream?: boolean;
	startTime: string | null;
	deploymentId?: string | null;
	includeReplayCounts?: boolean;
	signal?: AbortSignal;
};

export async function fetchPlan(options: FetchPlanOptions): Promise<Plan> {
	const project: Project | null = getAppInstance().app.project;
	if (project === null) throw new Error('fetchPlan() called before the app finished loading');
	return planFromServer(await requestPlan(options), project.adapter);
}
