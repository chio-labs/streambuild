import { describe, expect, it } from 'vitest';

import { planStatusFor } from '$lib/plan-view/_helpers/plan-status';
import type { Plan } from '$lib/planning/types';

const PLAN: Plan = { command: 'stb build', deploymentId: null, mode: 'direct' } as unknown as Plan;

describe('plan status', () => {
	it('given a failed request when reducing then the status is error even with an earlier plan', () => {
		expect(planStatusFor({ planError: 'boom', planLoading: false, plan: PLAN })).toBe('error');
	});

	it('given a pending re-plan when reducing then the status is loading not the earlier plan', () => {
		expect(planStatusFor({ planError: null, planLoading: true, plan: PLAN })).toBe('loading');
	});

	it('given a resolved plan when reducing then the status is ready', () => {
		expect(planStatusFor({ planError: null, planLoading: false, plan: PLAN })).toBe('ready');
	});

	it('given no plan and no request when reducing then the status is empty', () => {
		expect(planStatusFor({ planError: null, planLoading: false, plan: null })).toBe('empty');
	});
});
