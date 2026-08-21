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
		expect(fetchMock.mock.calls[1][1]).toEqual({ headers: undefined, signal: undefined });
	});

	it('given cached definitions when the server returns not modified then the session copy is reused', async () => {
		const storage: Map<string, string> = new Map([
			['streambuild:definitions:version-1', '{"models":[{"name":"orders"}]}']
		]);
		vi.stubGlobal('sessionStorage', {
			getItem: (key: string) => storage.get(key) ?? null,
			setItem: (key: string, value: string) => storage.set(key, value)
		});
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response(null, { status: 304 }))
		);
		vi.stubGlobal('fetch', fetchMock);

		const definitions: Record<string, unknown> = await requestDefinitionsPayload('version-1');

		expect(definitions).toEqual({ models: [{ name: 'orders' }] });
		expect(fetchMock).toHaveBeenCalledWith('/api/definitions', {
			headers: { 'If-None-Match': '"version-1"' },
			signal: undefined
		});
	});

	it('given no cached definitions when a version is known then the complete payload is requested', async () => {
		vi.stubGlobal('sessionStorage', {
			getItem: () => null,
			setItem: vi.fn()
		});
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValue(new Response('{"models":[]}'));
		vi.stubGlobal('fetch', fetchMock);

		const definitions: Record<string, unknown> = await requestDefinitionsPayload('version-1');

		expect(definitions).toEqual({ models: [] });
		expect(fetchMock).toHaveBeenCalledWith('/api/definitions', {
			headers: undefined,
			signal: undefined
		});
	});
});
