import { describe, expect, it } from 'vitest';

import { parseUnifiedDiff } from '$lib/presentation/main/_parse-unified-diff';
import type { UnifiedDiff } from '$lib/presentation/types';

const ORDERS_DIFF: string = [
	'--- previous',
	'+++ current',
	'@@ -1,3 +1,3 @@',
	' SELECT order_id,',
	'-  amount',
	'+  amount, customer_id',
	' FROM orders',
	''
].join('\n');

describe('unified diff parsing', () => {
	it('given a diff when parsed then each line is classified with its prefix removed', () => {
		const parsed: UnifiedDiff = parseUnifiedDiff(ORDERS_DIFF);

		expect(parsed.lines).toEqual([
			{ kind: 'header', sign: '', text: '--- previous' },
			{ kind: 'header', sign: '', text: '+++ current' },
			{ kind: 'hunk', sign: '', text: '@@ -1,3 +1,3 @@' },
			{ kind: 'context', sign: '', text: 'SELECT order_id,' },
			{ kind: 'del', sign: '−', text: '  amount' },
			{ kind: 'add', sign: '+', text: '  amount, customer_id' },
			{ kind: 'context', sign: '', text: 'FROM orders' }
		]);
	});

	it('given file headers when counted then only content lines are added or removed', () => {
		const parsed: UnifiedDiff = parseUnifiedDiff(ORDERS_DIFF);

		expect([parsed.added, parsed.removed]).toEqual([1, 1]);
	});

	it('given header-like content inside a hunk when parsed then it is content', () => {
		const parsed: UnifiedDiff = parseUnifiedDiff(
			['--- previous', '+++ current', '@@ -1,2 +1,2 @@', '--- legacy note', '+++ new note'].join(
				'\n'
			)
		);

		expect(parsed.lines.slice(3)).toEqual([
			{ kind: 'del', sign: '−', text: '-- legacy note' },
			{ kind: 'add', sign: '+', text: '++ new note' }
		]);
		expect([parsed.added, parsed.removed]).toEqual([1, 1]);
	});

	it('given more than two header-like lines before a hunk when parsed then only two are headers', () => {
		const parsed: UnifiedDiff = parseUnifiedDiff(
			['--- previous', '+++ current', '--- stray'].join('\n')
		);

		expect(parsed.lines.map((line) => line.kind)).toEqual(['header', 'header', 'del']);
	});

	it('given no diff when parsed then nothing is rendered or counted', () => {
		expect([parseUnifiedDiff(''), parseUnifiedDiff(null), parseUnifiedDiff(undefined)]).toEqual([
			{ lines: [], added: 0, removed: 0 },
			{ lines: [], added: 0, removed: 0 },
			{ lines: [], added: 0, removed: 0 }
		]);
	});
});
