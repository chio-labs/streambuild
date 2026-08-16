import { requestWithAuthentication } from '../_api/authenticated-fetch';

export function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
	return requestWithAuthentication(input, init);
}
