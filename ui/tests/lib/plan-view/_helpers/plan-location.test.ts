import { describe, expect, it } from 'vitest';

import {
	readPlanLocation,
	planLocationRequestKey,
	writePlanDeployment,
	writePlanSelection
} from '$lib/plan-view/_helpers/plan-location';

describe('plan location', () => {
	it('given a planned deployment when selection changes then the stale deployment is removed', () => {
		const current: URL = new URL(
			'https://example.test/plan?select=model%3Aorders&start=2026-08-10T12%3A00%3A00Z&deployment=20260810T120000Z_old'
		);

		const next: URL = writePlanSelection(
			current,
			[{ kind: 'model', name: 'payments' }],
			{ mode: 'from', startTime: '2026-08-10T12:00:00Z' }
		);

		expect(next.searchParams.get('deployment')).toBeNull();
		expect(readPlanLocation(next).deploymentId).toBeNull();
	});

	it('given a generated deployment when canonicalizing then other plan inputs are preserved', () => {
		const current: URL = new URL(
			'https://example.test/plan?select=model%3Aorders&start=2026-08-10T12%3A00%3A00Z'
		);

		const next: URL = writePlanDeployment(current, '20260811T120000Z_plan');

		expect(next.searchParams.get('select')).toBe('model:orders');
		expect(next.searchParams.get('start')).toBe('2026-08-10T12:00:00Z');
		expect(readPlanLocation(next).deploymentId).toBe('20260811T120000Z_plan');
	});

	it('given equivalent plan parameters when request keys are compared then they match', () => {
		const current: URL = new URL(
			'https://example.test/plan?select=orders&start=2026-08-10T12%3A00%3A00Z&deployment=20260811T120000Z_plan'
		);
		const reordered: URL = new URL(
			'https://example.test/plan?deployment=20260811T120000Z_plan&start=2026-08-10T12%3A00%3A00Z&select=orders'
		);

		expect(planLocationRequestKey(reordered)).toBe(planLocationRequestKey(current));
	});
});
