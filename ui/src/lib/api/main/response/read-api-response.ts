import { readApiResponse as readResponse } from '$lib/api/_api/read-response';

export async function readApiResponse<T>(response: Response, operation: string): Promise<T> {
	return readResponse<T>(response, operation);
}
