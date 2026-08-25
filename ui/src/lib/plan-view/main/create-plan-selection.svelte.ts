import {
	planLocationRequestKey,
	readPlanLocation,
	writePlanSelection
} from '$lib/plan-view/_helpers/plan-location';
import type { ParsedPlanLocation } from '$lib/plan-view/types';
import type { ReplayWindow, Selector } from '$lib/planning/types';

type PlanSelectionOptions = {
	currentUrl(): URL;
	navigate(url: URL): void;
};

type PlanSelection = {
	readonly location: ParsedPlanLocation;
	apply(
		selectors: Selector[],
		replayWindow?: ReplayWindow,
		deploymentId?: string | null,
		changed?: boolean,
		includeMissingUpstream?: boolean
	): void;
	setSelectors(selectors: Selector[]): void;
	setChanged(changed: boolean): void;
	setIncludeMissingUpstream(includeMissingUpstream: boolean): void;
	setReplayWindow(replayWindow: ReplayWindow): void;
};

export function createPlanSelection(options: PlanSelectionOptions): PlanSelection {
	const location: ParsedPlanLocation = $derived(readPlanLocation(options.currentUrl()));

	function apply(
		selectors: Selector[],
		replayWindow?: ReplayWindow,
		deploymentId: string | null = null,
		changed: boolean = location.changed,
		includeMissingUpstream: boolean = location.includeMissingUpstream
	): void {
		const currentUrl: URL = options.currentUrl();
		const nextUrl: URL = writePlanSelection(
			currentUrl,
			selectors,
			replayWindow,
			deploymentId,
			changed,
			includeMissingUpstream
		);
		if (planLocationRequestKey(nextUrl) === planLocationRequestKey(currentUrl)) return;
		options.navigate(nextUrl);
	}

	return {
		get location() {
			return location;
		},
		apply,
		setSelectors(selectors: Selector[]): void {
			apply(
				selectors,
				selectors.length === 0 ? { mode: 'full' } : undefined,
				null,
				false,
				selectors.length > 0 && location.includeMissingUpstream
			);
		},
		setChanged(changed: boolean): void {
			apply(
				[],
				changed ? undefined : { mode: 'full' },
				null,
				changed,
				changed && location.includeMissingUpstream
			);
		},
		setIncludeMissingUpstream(includeMissingUpstream: boolean): void {
			apply(location.selectors, undefined, null, location.changed, includeMissingUpstream);
		},
		setReplayWindow(replayWindow: ReplayWindow): void {
			apply(
				location.selectors,
				location.selectors.length === 0 && !location.changed ? { mode: 'full' } : replayWindow
			);
		}
	};
}
