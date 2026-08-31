import { buildLineageSnapshot } from '$lib/lineage-view/_helpers/lineage-snapshot';
import {
	writeLineageFilters,
	writeLineageToggle,
	writeLineageValue,
	readLineageMode
} from '$lib/lineage-view/_helpers/lineage-location';
import type { LineageViewFacade } from '$lib/lineage-view/types';

export function createLineageView(): LineageViewFacade {
	return {
		snapshot: buildLineageSnapshot,
		filtersUrl: writeLineageFilters,
		deploymentsUrl: (url, showDeployments) =>
			writeLineageToggle(url, 'deployments', showDeployments),
		groupUrl: (url, groupMode) =>
			writeLineageValue(
				url,
				'group',
				groupMode,
				readLineageMode(url) === 'physical' ? 'boxes' : 'lanes'
			),
		modeUrl: (url, mode) => writeLineageValue(url, 'mode', mode, 'logical')
	};
}
