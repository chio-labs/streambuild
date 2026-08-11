import { auditCounts } from '$lib/domain/main/quality/audit-counts';
import { auditsForModel } from '$lib/domain/main/quality/audits-for-model';
import type { PipelineViewFacade } from '$lib/pipeline-view/types';
import type { Project } from '$lib/domain/types';

export function countModelAudits(
	project: Project,
	modelName: string
): ReturnType<PipelineViewFacade['auditCounts']> {
	return auditCounts(auditsForModel(project, modelName));
}
