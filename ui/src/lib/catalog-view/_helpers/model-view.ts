import { modelByName } from '$lib/domain/main/lookups/model-by-name';
import { auditsForModel } from '$lib/domain/main/quality/audits-for-model';
import { testsForModel } from '$lib/domain/main/quality/tests-for-model';
import { reconstructionCoverage } from '$lib/domain/main/reconstruction/reconstruction-coverage';
import { rootSourceFor } from '$lib/domain/main/reconstruction/root-source-for';
import type { CatalogModelView } from '$lib/catalog-view/types';
import type { Model, Project } from '$lib/domain/types';

export function buildCatalogModelView(project: Project, modelName: string): CatalogModelView {
	const model: Model | undefined = modelByName(project, modelName);
	return {
		model,
		audits: model ? auditsForModel(project, model.name) : [],
		tests: model ? testsForModel(project, model.name) : [],
		source: model ? rootSourceFor(project, model) : undefined,
		coverage: reconstructionCoverage(project).find((row) => row.modelName === modelName),
		artifacts: model
			? [
					{ label: 'Authored SQL', code: model.sql.authored },
					{ label: 'Compiled SQL', code: model.sql.compiled },
					{
						label: 'Live DDL',
						code: model.live.semanticDrift.liveDdl,
						note: 'Observed from the live warehouse at the current snapshot.'
					},
					{ label: 'Table DDL', code: model.sql.tableDdl },
					{ label: 'MV DDL', code: model.sql.mvDdl },
					{ label: 'View DDL', code: model.sql.viewDdl }
				]
			: [],
		upstream: model?.refs ?? [],
		downstream: project.models.filter((candidate) =>
			candidate.refs.some((ref) => !ref.isSource && ref.name === modelName)
		)
	};
}
