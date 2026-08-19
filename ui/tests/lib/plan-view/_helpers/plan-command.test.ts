import { describe, expect, it } from 'vitest';

import { parsePlanCommand } from '$lib/plan-view/_helpers/plan-command';

describe('plan command', () => {
	it('given a virtual build command when parsed then its deployment identity is retained', () => {
		const parsed: ReturnType<typeof parsePlanCommand> = parsePlanCommand(
			'stb build --select orders --start-time 2026-08-10T12:00:00Z --deployment-id 20260811T120000Z_plan'
		);

		expect(parsed.deploymentId).toBe('20260811T120000Z_plan');
		expect(parsed.selectors).toEqual([{ kind: 'model', name: 'orders' }]);
		expect(parsed.replayWindow).toEqual({
			mode: 'from',
			startTime: '2026-08-10T12:00:00.000Z'
		});
	});

	it('given one --select flag with several names when parsing then every name becomes a selector', () => {
		const parsed: ReturnType<typeof parsePlanCommand> = parsePlanCommand(
			'stb build --select orders pipeline:pl__payments revenue'
		);

		expect(parsed.selectors).toEqual([
			{ kind: 'model', name: 'orders' },
			{ kind: 'pipeline', name: 'pl__payments' },
			{ kind: 'model', name: 'revenue' }
		]);
	});
});
