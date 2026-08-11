import { requestPlan } from '$lib/api/_api/plan';
import { planFromServer } from '$lib/api/_helpers/mapping';
import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';
import type { Project } from '$lib/domain/types';
import type { Plan } from '$lib/planning/types';

export async function fetchPlan(
	selectors: string[],
	startTime: string | null,
	deploymentId: string | null = null
): Promise<Plan> {
	const project: Project | null = getAppInstance().app.project;
	if (project === null) throw new Error('fetchPlan() called before the app finished loading');
	return planFromServer(await requestPlan(selectors, startTime, deploymentId), project.adapter);
}
