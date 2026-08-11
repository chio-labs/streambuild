import { REF_TYPE_LABEL } from '$lib/domain/constants';
import { formatAgo } from '$lib/formatting/main/format-ago';
import { formatCompact } from '$lib/formatting/main/format-compact';
import { formatDuration } from '$lib/formatting/main/format-duration';
import { formatRate } from '$lib/formatting/main/format-rate';
import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
import { countModelAudits } from '$lib/pipeline-view/_helpers/model-audits';
import { buildPipelineSnapshot } from '$lib/pipeline-view/_helpers/pipeline-snapshot';
import type { PipelineViewFacade } from '$lib/pipeline-view/types';

export function createPipelineView(): PipelineViewFacade {
	return {
		snapshot: buildPipelineSnapshot,
		auditCounts: countModelAudits,
		formatAgo,
		formatCompact,
		formatDuration,
		formatRate,
		formatTimestamp,
		refTypeLabel: REF_TYPE_LABEL
	};
}
