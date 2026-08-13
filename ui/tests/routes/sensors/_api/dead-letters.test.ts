import { afterEach, describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import {
	fetchDeadLetters,
	requestDeadLetterRetry,
	requestDeadLetterSkip
} from '../../../../src/routes/sensors/_api/dead-letters';
import type { DeadLettersPayload } from '../../../../src/routes/sensors/types';

describe('dead letters API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given dead letters when requested then the typed queue is returned', async () => {
		const payload: DeadLettersPayload = { deadLetters: [] };
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValue(new Response(JSON.stringify(payload)));
		vi.stubGlobal('fetch', fetchMock);

		const result: DeadLettersPayload = await fetchDeadLetters();

		expect(result).toEqual(payload);
		expect(fetchMock).toHaveBeenCalledWith('/api/sensors/dead-letters', { signal: undefined });
	});

	it('given retry and skip actions when requested then exact payloads are posted', async () => {
		authenticatedFetch.mockImplementation(() =>
			Promise.resolve(
				new Response(JSON.stringify({ sensorName: 'a', eventId: 'e', status: 'succeeded' }))
			)
		);

		await requestDeadLetterRetry('quality_alerts', 'event-1');
		await requestDeadLetterSkip('quality_alerts', 'event-1', 'acknowledged');

		expect(authenticatedFetch).toHaveBeenNthCalledWith(1, '/api/sensors/dead-letters/retry', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ sensorName: 'quality_alerts', eventId: 'event-1' })
		});
		expect(authenticatedFetch).toHaveBeenNthCalledWith(2, '/api/sensors/dead-letters/skip', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				sensorName: 'quality_alerts',
				eventId: 'event-1',
				reason: 'acknowledged'
			})
		});
	});
});
