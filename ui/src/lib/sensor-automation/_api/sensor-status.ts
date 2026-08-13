import { readApiResponse } from '$lib/api/main/response/read-api-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

import type { SensorStatusResult } from '../types';

export async function requestSensorStatus(
	sensorName: string,
	status: string
): Promise<SensorStatusResult> {
	const response: Response = await authenticatedFetch(
		`/api/sensors/${encodeURIComponent(sensorName)}/status`,
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ status })
		}
	);
	return readApiResponse<SensorStatusResult>(response, 'sensor status');
}
