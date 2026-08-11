import { afterEach, describe, expect, it, vi } from 'vitest';

import {
	requestDefinitionsPayload,
	requestStatePayload,
	requestStatusPayload
} from '$lib/api/_api/project';

describe('project API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given project reads when requested then endpoints return JSON and unavailable state becomes null', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValueOnce(new Response('{"state":"ok"}'))
			.mockResolvedValueOnce(new Response('{"models":[]}'))
			.mockResolvedValueOnce(new Response('unavailable', { status: 503 }));
		vi.stubGlobal('fetch', fetchMock);

		const status: Record<string, unknown> = await requestStatusPayload();
		const definitions: Record<string, unknown> = await requestDefinitionsPayload();
		const state: Record<string, unknown> | null = await requestStatePayload();

		expect(status).toEqual({ state: 'ok' });
		expect(definitions).toEqual({ models: [] });
		expect(state).toBeNull();
		expect(fetchMock.mock.calls.map((call: unknown[]) => call[0])).toEqual([
			'/api/status',
			'/api/definitions',
			'/api/state'
		]);
	});
});
