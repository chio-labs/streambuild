import { readApiResponse } from '$lib/api/main/response/read-api-response';

import type { SensorsPayload, SensorTicksPayload } from '../types';

export async function fetchSensors(signal?: AbortSignal): Promise<SensorsPayload> {
	const response: Response = await fetch('/api/sensors', { signal });
	return readApiResponse<SensorsPayload>(response, 'sensors');
}

export async function fetchSensorTicks(
	sensorName: string,
	signal?: AbortSignal
): Promise<SensorTicksPayload> {
	const response: Response = await fetch(
		`/api/sensors/${encodeURIComponent(sensorName)}/ticks`,
		{ signal }
	);
	return readApiResponse<SensorTicksPayload>(response, 'sensor ticks');
}
