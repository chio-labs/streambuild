import { describe, expect, it } from 'vitest';

import {
	readPlanLocation,
	planLocationRequestKey,
	writePlanDeployment,
	writePlanSelection
} from '$lib/plan-view/_helpers/plan-location';
import type { ParsedPlanLocation } from '$lib/plan-view/types';

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

	it('given changed mode and missing upstream when read then both flags are retained without selectors', () => {
		const current: URL = new URL(
			'https://example.test/plan?select=orders&changed=1&include_missing_upstream=1'
		);

		expect(readPlanLocation(current)).toMatchObject({
			selectors: [],
			changed: true,
			includeMissingUpstream: true
		});
	});

	it('given changed mode when a selection is written then the location uses both boolean fields', () => {
		const next: URL = writePlanSelection(
			new URL('https://example.test/plan?select=orders'),
			[],
			{ mode: 'full' },
			null,
			true,
			true
		);

		expect(next.search).toBe('?changed=1&include_missing_upstream=1');
		expect(planLocationRequestKey(next)).not.toBe(
			planLocationRequestKey(new URL('https://example.test/plan'))
		);
	});

	it('given changed plan flags when deployment is canonicalized then both are preserved', () => {
		const next: URL = writePlanDeployment(
			new URL('https://example.test/plan?changed=1&include_missing_upstream=1'),
			'20260811T120000Z_plan'
		);

		expect(next.searchParams.get('changed')).toBe('1');
		expect(next.searchParams.get('include_missing_upstream')).toBe('1');
	});

	it('given missing-upstream without a selection when read then the invalid flag is ignored', () => {
		const location: ParsedPlanLocation = readPlanLocation(
			new URL('https://example.test/plan?include_missing_upstream=1')
		);

		expect(location.includeMissingUpstream).toBe(false);
	});
});
