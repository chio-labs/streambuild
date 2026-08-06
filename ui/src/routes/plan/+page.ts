/**
 * Fetch the plan DURING navigation, not after mount — otherwise the plan graph
 * pops in a round-trip after the page renders. On a cold deep link the app
 * store is not initialized yet (the layout gate is still on the loading
 * screen), so we bail to nulls and let the page's own effect fetch instead.
 */

import { app } from '$lib/api/store.svelte';
import { fetchPlan } from '$lib/api';
import type { Plan } from '$lib/domain/types';

export type PlanPageData = {
	initialPlan: Plan | null;
	initialKey: string | null;
};

export const load = async ({ url }: { url: URL }): Promise<PlanPageData> => {
	if (app.project === null) return { initialPlan: null, initialKey: null };
	const tokens: string[] = url.searchParams.getAll('select');
	const start: string | null = url.searchParams.get('start');
	const key: string = `${tokens.join(',')}|${start ?? ''}`;
	try {
		return { initialPlan: await fetchPlan(tokens, start), initialKey: key };
	} catch {
		return { initialPlan: null, initialKey: null };
	}
};
