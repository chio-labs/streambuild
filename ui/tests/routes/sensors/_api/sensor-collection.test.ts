import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchSensors, fetchSensorTicks } from '../../../../src/routes/sensors/_api/sensor-collection';
import type { SensorsPayload, SensorTicksPayload } from '../../../../src/routes/sensors/types';

describe('sensor collection API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a sensors payload when requested then typed sensors are returned', async () => {
		const payload: SensorsPayload = {
			sensors: [],
			deadLetterCount: 0,
			health: {
				state: 'idle',
				consecutiveErrors: 0,
				latestError: null,
				backoffSeconds: 0,
				nextTickSeconds: 10,
				lastSuccessfulTick: null,
				lastEvaluatedCount: null,
				leaseHeld: null
			}
		};
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValue(new Response(JSON.stringify(payload)));
		vi.stubGlobal('fetch', fetchMock);

		const result: SensorsPayload = await fetchSensors();

		expect(result).toEqual(payload);
		expect(fetchMock).toHaveBeenCalledWith('/api/sensors', { signal: undefined });
	});

	it('given tick history when requested then the sensor name is encoded', async () => {
		const payload: SensorTicksPayload = { sensorName: 'quality alerts', ticks: [] };
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValue(new Response(JSON.stringify(payload)));
		vi.stubGlobal('fetch', fetchMock);

		const result: SensorTicksPayload = await fetchSensorTicks('quality alerts');

		expect(result).toEqual(payload);
		expect(fetchMock).toHaveBeenCalledWith('/api/sensors/quality%20alerts/ticks', {
			signal: undefined
		});
	});
});
