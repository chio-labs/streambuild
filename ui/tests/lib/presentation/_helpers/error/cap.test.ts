import { describe, expect, it } from 'vitest';

import {
	capErrorText,
	formatByteSize,
	type CappedText
} from '$lib/presentation/_helpers/error/cap';

describe('capErrorText', () => {
	it('given text within the limit when capping then it is returned untouched', () => {
		const result: CappedText = capErrorText('short error', 1024);

		expect(result).toEqual({ text: 'short error', truncatedBytes: 0, isTruncated: false });
	});

	it('given oversized ascii when capping then the head is kept and the tail byte count is reported', () => {
		const text: string = 'x'.repeat(100);

		const result: CappedText = capErrorText(text, 40);

		expect(result.isTruncated).toBe(true);
		expect(result.text).toBe('x'.repeat(40));
		expect(result.truncatedBytes).toBe(60);
	});

	it('given a multibyte code point straddling the limit when capping then it is never split', () => {
		// Each rocket is 4 UTF-8 bytes; a 10-byte budget fits two whole rockets.
		const text: string = '🚀🚀🚀';

		const result: CappedText = capErrorText(text, 10);

		expect(result.text).toBe('🚀🚀');
		expect(result.truncatedBytes).toBe(4);
		expect(new TextEncoder().encode(result.text).length).toBeLessThanOrEqual(10);
	});
});

describe('formatByteSize', () => {
	it('given byte magnitudes when formatting then the unit scales', () => {
		expect(formatByteSize(512)).toBe('512 B');
		expect(formatByteSize(2048)).toBe('2 KB');
		expect(formatByteSize(3 * 1024 * 1024)).toBe('3.0 MB');
	});
});
