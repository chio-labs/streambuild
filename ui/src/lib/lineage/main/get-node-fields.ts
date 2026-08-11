import { getNodeFieldsInstance } from '$lib/lineage/_helpers/node-fields-instance.svelte';
import type { NodeFieldController } from '$lib/lineage/types';

export function getNodeFields(): NodeFieldController {
	return getNodeFieldsInstance();
}
