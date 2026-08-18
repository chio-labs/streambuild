import { readApiResponse } from '$lib/api/_api/read-response';
import type { RunStatement } from '$lib/api/types';

export async function requestRunStatement(
	invocationId: string,
	statementSequence: number
): Promise<RunStatement> {
	const response: Response = await fetch(
		`/api/runs/${encodeURIComponent(invocationId)}/statements/${statementSequence}`
	);
	return readApiResponse<RunStatement>(response, 'run statement');
}
