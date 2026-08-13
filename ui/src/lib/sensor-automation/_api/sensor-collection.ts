import { readApiResponse } from '$lib/api/main/response/read-api-response';

import type { SensorsPayload, SensorTicksPayload } from '../types';

export async function fetchSensors(signal?: AbortSignal): Promise<SensorsPayload> {
	const response: Response = await fetch('/api/sensors', { signal });
	return readApiResponse<SensorsPayload>(response, 'sensors');
}

export async function fetchSensorTicks(
	sensorName: string,
	signal?: AbortSignal,
	window?: { after: string; before: string; limit: number }
): Promise<SensorTicksPayload> {
	const query: URLSearchParams = new URLSearchParams();
	if (window) {
		query.set('after', window.after);
		query.set('before', window.before);
		query.set('limit', String(window.limit));
	}
	const suffix: string = window ? `?${query.toString()}` : '';
	const response: Response = await fetch(
		`/api/sensors/${encodeURIComponent(sensorName)}/ticks${suffix}`,
		{ signal }
	);
	return readApiResponse<SensorTicksPayload>(response, 'sensor ticks');
}
