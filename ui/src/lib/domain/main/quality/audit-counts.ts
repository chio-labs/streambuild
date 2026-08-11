import { domainDerivations } from '$lib/domain/_helpers/derive';
import type { Audit } from '$lib/domain/types';

export function auditCounts(
	audits: Audit[]
): ReturnType<typeof domainDerivations.auditCounts> {
	return domainDerivations.auditCounts(audits);
}
