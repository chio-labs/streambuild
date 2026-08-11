import type { LineageFilterState, NodeKindFilter } from '$lib/lineage-view/types';
import type { GraphMode } from '$lib/lineage/types';
import type { ModelStatus } from '$lib/domain/types';

export function readLineageMode(url: URL): GraphMode {
	return url.searchParams.get('mode') === 'physical' ? 'physical' : 'logical';
}

export function readLineageFilters(url: URL): LineageFilterState {
	const params: URLSearchParams = url.searchParams;
	return {
		search: params.get('q') ?? '',
		pipelines: new Set(params.getAll('pipeline')),
		kinds: new Set(params.getAll('kind') as NodeKindFilter[]),
		statuses: new Set(params.getAll('status') as ModelStatus[]),
		anchorsOnly: params.get('anchors') === '1'
	};
}

export function writeLineageFilters(url: URL, filters: LineageFilterState): URL {
	const nextUrl: URL = new URL(url);
	for (const key of ['q', 'pipeline', 'kind', 'status', 'anchors']) nextUrl.searchParams.delete(key);
	if (filters.search.trim()) nextUrl.searchParams.set('q', filters.search.trim());
	for (const value of filters.pipelines) nextUrl.searchParams.append('pipeline', value);
	for (const value of filters.kinds) nextUrl.searchParams.append('kind', value);
	for (const value of filters.statuses) nextUrl.searchParams.append('status', value);
	if (filters.anchorsOnly) nextUrl.searchParams.set('anchors', '1');
	return nextUrl;
}

export function writeLineageToggle(url: URL, key: string, enabled: boolean): URL {
	const nextUrl: URL = new URL(url);
	if (enabled) nextUrl.searchParams.set(key, '1');
	else nextUrl.searchParams.delete(key);
	return nextUrl;
}

export function writeLineageValue(url: URL, key: string, value: string, defaultValue: string): URL {
	const nextUrl: URL = new URL(url);
	if (value === defaultValue) nextUrl.searchParams.delete(key);
	else nextUrl.searchParams.set(key, value);
	return nextUrl;
}
