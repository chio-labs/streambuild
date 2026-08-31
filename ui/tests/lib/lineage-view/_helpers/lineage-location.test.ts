import { describe, expect, it } from 'vitest';
import { readLineageGroupMode } from '$lib/lineage-view/_helpers/lineage-location';

describe('lineage location', () => {
	it('given URLs without grouping when reading lineage mode then uses scale-safe defaults', () => {
		expect(readLineageGroupMode(new URL('http://streambuild/lineage'))).toBe('lanes');
		expect(readLineageGroupMode(new URL('http://streambuild/lineage?mode=physical'))).toBe('boxes');
	});

	it('given explicit physical grouping when reading lineage mode then preserves full detail', () => {
		expect(
			readLineageGroupMode(new URL('http://streambuild/lineage?mode=physical&group=none'))
		).toBe('none');
		expect(
			readLineageGroupMode(new URL('http://streambuild/lineage?mode=physical&group=lanes'))
		).toBe('lanes');
	});
});
