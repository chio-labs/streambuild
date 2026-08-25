import { afterEach, describe, expect, it } from 'vitest';

import { domainFormatters } from '$lib/formatting/_helpers/format';

describe('configured timestamp timezone', () => {
	afterEach(() => domainFormatters.configureTimeZone('UTC'));

	it('given a London timezone when formatting a summer instant then applies daylight saving time', () => {
		domainFormatters.configureTimeZone('Europe/London');

		expect(domainFormatters.formatTimestamp('2026-08-25T14:30:00Z')).toBe(
			'2026-08-25 15:30:00'
		);
		expect(domainFormatters.formatClock('2026-08-25T14:30:00Z')).toBe('15:30:00');
	});
});
