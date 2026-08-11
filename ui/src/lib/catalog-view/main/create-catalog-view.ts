import { OWNERSHIP_LABEL, REF_TYPE_LABEL } from '$lib/domain/constants';
import { formatAgo } from '$lib/formatting/main/format-ago';
import { formatBytes } from '$lib/formatting/main/format-bytes';
import { formatDaySpan } from '$lib/formatting/main/format-day-span';
import { formatDuration } from '$lib/formatting/main/format-duration';
import { formatInteger } from '$lib/formatting/main/format-integer';
import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
import { buildCatalogModelView } from '$lib/catalog-view/_helpers/model-view';
import type { CatalogViewFacade } from '$lib/catalog-view/types';

export function createCatalogView(): CatalogViewFacade {
	return {
		modelView: buildCatalogModelView,
		formatAgo,
		formatBytes,
		formatDaySpan,
		formatDuration,
		formatInteger,
		formatTimestamp,
		ownershipLabel: OWNERSHIP_LABEL,
		refTypeLabel: REF_TYPE_LABEL
	};
}
