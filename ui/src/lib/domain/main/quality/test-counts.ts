import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { SqlTest } from '$lib/domain/types';

export function testCounts(tests: SqlTest[]): ReturnType<typeof domainDerivations.testCounts> {
	return domainDerivations.testCounts(tests);
}
