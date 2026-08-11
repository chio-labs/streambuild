import { afterEach, describe, expect, it, vi } from 'vitest';

import { createVisibilityResource } from '$lib/api/_resources/visibility.resource';

describe('visibility resource', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given visibility changes when the resource is active then refresh runs only after becoming visible', () => {
		const documentStub: EventTarget & { hidden: boolean } = Object.assign(new EventTarget(), {
			hidden: true
		});
		const refresh = vi.fn<() => Promise<void>>(() => Promise.resolve());
		const resource: ReturnType<typeof createVisibilityResource> = createVisibilityResource(refresh);
		vi.stubGlobal('document', documentStub);

		resource.start();
		documentStub.dispatchEvent(new Event('visibilitychange'));
		documentStub.hidden = false;
		documentStub.dispatchEvent(new Event('visibilitychange'));
		resource.stop();
		documentStub.dispatchEvent(new Event('visibilitychange'));

		expect(refresh).toHaveBeenCalledTimes(1);
	});
});
