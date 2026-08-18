import { requestRunStatement } from '$lib/api/_api/run-statement';
import type { RunStatement } from '$lib/api/types';

export async function fetchRunStatement(
	invocationId: string,
	statementSequence: number
): Promise<RunStatement> {
	return requestRunStatement(invocationId, statementSequence);
}
