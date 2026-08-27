import type { Model, Pipeline, Source } from '$lib/domain/types';

type SearchablePipelineRow = {
	pipeline: Pick<Pipeline, 'name'>;
	models: Pick<Model, 'name' | 'relationName'>[];
	source: Pick<Source, 'name'> | undefined;
};

export function filterPipelineRows<T extends SearchablePipelineRow>(
	rows: T[],
	query: string
): T[] {
	const normalizedQuery: string = query.trim().toLowerCase();
	if (!normalizedQuery) return rows;
	return rows.filter((row) => {
		const searchable: string = [
			row.pipeline.name,
			row.source?.name ?? '',
			...row.models.flatMap((model) => [model.name, model.relationName])
		]
			.join(' ')
			.toLowerCase();
		return searchable.includes(normalizedQuery);
	});
}
