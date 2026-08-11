import type { RunEvent } from '$lib/api/types';
import { buildRunActivity } from '$lib/run-presentation/_helpers/run-activity';
import { labelRunEvent } from '$lib/run-presentation/_helpers/run-event-label';
import { buildRunGraph } from '$lib/run-presentation/_helpers/run-graph';
import { buildRunEventLabelContext } from '$lib/run-presentation/_helpers/run-step-counts';
import { buildTimeline } from '$lib/run-presentation/_helpers/timeline';
import { RUN_OUTCOME_COLORS } from '$lib/run-presentation/constants';
import type {
	RunActivityPresentation,
	RunEventLabelContext,
	RunGraphPresentation,
	RunPresentation,
	RunPresentationInput
} from '$lib/run-presentation/types';

export function buildRunPresentation(input: RunPresentationInput): RunPresentation {
	const activity: RunActivityPresentation = buildRunActivity(input);
	const graph: RunGraphPresentation = buildRunGraph({
		project: input.project,
		events: input.events,
		running: input.running,
		outcome: input.status,
		startedEvent: activity.startedEvent,
		record: input.record,
		commandLine: input.commandLine
	});
	const timeline: RunEvent[] = buildTimeline(input.events, input.running);
	const labelContext: RunEventLabelContext = buildRunEventLabelContext(
		input.events,
		activity.displayCommand
	);
	const eventLabels: Map<number, string> = new Map(
		timeline.map((event: RunEvent): [number, string] => [
			event.sequence,
			labelRunEvent(event, labelContext)
		])
	);
	return {
		...activity,
		...graph,
		outcome: input.status,
		outcomeColor: RUN_OUTCOME_COLORS[input.status],
		timeline,
		eventLabels
	};
}
