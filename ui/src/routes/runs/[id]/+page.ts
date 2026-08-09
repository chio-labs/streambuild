import type { PageLoad } from './$types';
import { prefetchRunDetail } from './state';

/** Preload the first durable snapshot; the page consumes this exact request. */
export const load: PageLoad = ({ params }): void => {
	void prefetchRunDetail(params.id).catch(() => undefined);
};
