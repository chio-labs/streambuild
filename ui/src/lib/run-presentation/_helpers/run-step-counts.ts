import type { RunEvent } from '$lib/api/types';
import type { RunEventLabelContext } from '$lib/run-presentation/types';

export function buildRunEventLabelContext(
	events: RunEvent[],
	displayCommand: string
): RunEventLabelContext {
	return {
		displayCommand,
		metadataPreparationCount: numberedStepCount(events, 'prepare_metadata_'),
		metadataMigrationCount: numberedStepCount(events, 'migrate_metadata_'),
		candidateMetadataCount: numberedStepCount(events, 'persist_candidate_metadata_'),
		publicationCount: numberedStepCount(events, 'persist_publish_event_'),
		reconcileCount: numberedStepCount(events, 'persist_reconcile_state_')
	};
}

function numberedStepCount(events: RunEvent[], prefix: string): number {
	return Math.max(
		0,
		...events.map((event: RunEvent): number => {
			const match: RegExpMatchArray | null | undefined = event.stepId?.match(
				new RegExp(`^${prefix}(\\d+)$`)
			);
			return match ? Number(match[1]) : 0;
		})
	);
}
