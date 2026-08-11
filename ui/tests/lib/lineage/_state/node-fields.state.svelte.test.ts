import { afterEach, describe, expect, it, vi } from 'vitest';

import { createNodeFieldsState } from '$lib/lineage/_state/node-fields.state.svelte';
import type { NodeFieldController } from '$lib/lineage/types';

describe('node fields state', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given persisted preferences when fields change then defaults are merged and updates are stored', () => {
		const getItem: ReturnType<typeof vi.fn> = vi.fn(() => '{"kind":false,"rows":true}');
		const setItem: ReturnType<typeof vi.fn> = vi.fn();
		vi.stubGlobal('localStorage', { getItem, setItem });
		const controller: NodeFieldController = createNodeFieldsState();

		expect(controller.value.kind).toBe(false);
		expect(controller.value.rows).toBe(true);
		expect(controller.value.status).toBe(true);

		controller.toggle('rows');
		expect(controller.value.rows).toBe(false);
		expect(setItem).toHaveBeenLastCalledWith('sb-node-fields', JSON.stringify(controller.value));

		controller.reset();
		expect(controller.value.kind).toBe(true);
		expect(controller.value.rows).toBe(false);
	});
});
