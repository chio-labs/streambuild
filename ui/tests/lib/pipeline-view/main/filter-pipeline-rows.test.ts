import { describe, expect, it } from 'vitest';

import { filterPipelineRows } from '$lib/pipeline-view/main/filter-pipeline-rows';
import type { Model, Pipeline, Source } from '$lib/domain/types';

type TestRow = {
	pipeline: Pick<Pipeline, 'name'>;
	models: Pick<Model, 'name' | 'relationName'>[];
	source: Pick<Source, 'name'> | undefined;
};

interface PipelineFilterTestCase {
	readonly description: string;
	readonly query: string;
	readonly expectedNames: string[];
}

const rows: TestRow[] = [
	{
		pipeline: { name: 'pl__orders' },
		source: { name: 'order_events' },
		models: [{ name: 'commerce_orders', relationName: 'tbl__commerce_orders' }]
	},
	{
		pipeline: { name: 'pl__payments' },
		source: undefined,
		models: [{ name: 'payment_totals', relationName: 'view__payment_totals' }]
	}
];

describe('pipeline row filtering', () => {
	it.each<PipelineFilterTestCase>([
		{ description: 'matches pipeline names case-insensitively', query: 'PL__ORDERS', expectedNames: ['pl__orders'] },
		{ description: 'matches source names', query: 'order_events', expectedNames: ['pl__orders'] },
		{ description: 'matches model names', query: 'payment_totals', expectedNames: ['pl__payments'] },
		{ description: 'matches physical relation names', query: 'tbl__commerce', expectedNames: ['pl__orders'] },
		{ description: 'returns every row for whitespace', query: '   ', expectedNames: ['pl__orders', 'pl__payments'] },
		{ description: 'returns no rows for missing text', query: 'missing', expectedNames: [] }
	])('$description', (testCase) => {
		expect(filterPipelineRows(rows, testCase.query).map((row) => row.pipeline.name)).toEqual(
			testCase.expectedNames
		);
	});
});
