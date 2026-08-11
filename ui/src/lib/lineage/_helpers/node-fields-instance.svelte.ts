import { createNodeFieldsState } from '$lib/lineage/_state/node-fields.state.svelte';
import type { NodeFieldController } from '$lib/lineage/types';

let instance: NodeFieldController | null = null;

export function getNodeFieldsInstance(): NodeFieldController {
	if (instance === null) instance = createNodeFieldsState();
	return instance;
}
