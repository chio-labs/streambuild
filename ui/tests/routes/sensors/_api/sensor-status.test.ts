import { describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import { requestSensorStatus } from '../../../../src/routes/sensors/_api/sensor-status';
import type { SensorStatusResult } from '../../../../src/routes/sensors/types';

describe('sensor status API', () => {
	it('given a status change when requested then the exact payload is posted', async () => {
		authenticatedFetch.mockResolvedValue(
			new Response(JSON.stringify({ sensorName: 'quality_alerts', status: 'running' }))
		);

		const result: SensorStatusResult = await requestSensorStatus('quality_alerts', 'running');

		expect(result).toEqual({ sensorName: 'quality_alerts', status: 'running' });
		expect(authenticatedFetch).toHaveBeenCalledWith('/api/sensors/quality_alerts/status', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ status: 'running' })
		});
	});
});
