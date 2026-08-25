import { parseUtc } from '$lib/formatting/main/parse-utc';
import { parseSelector } from '$lib/planning/main/parse-selector';
import { selectorToken } from '$lib/planning/main/selector-token';
import type { ParsedPlanLocation } from '$lib/plan-view/types';
import type { ReplayWindow, Selector } from '$lib/planning/types';

export function replayStartToken(replayWindow: ReplayWindow): string | null {
	if (replayWindow.mode === 'full') return null;
	const parsed: Date = parseUtc(replayWindow.startTime);
	if (!Number.isFinite(parsed.getTime())) return null;
	return `${parsed.toISOString().slice(0, 19)}Z`;
}

export function readPlanLocation(url: URL): ParsedPlanLocation {
	const changed: boolean = url.searchParams.get('changed') === '1';
	const selectors: Selector[] = (changed ? [] : url.searchParams
		.getAll('select')
		.map(parseSelector)
		.filter((selector): selector is Selector => selector !== null));
	const includeMissingUpstream: boolean =
		url.searchParams.get('include_missing_upstream') === '1' &&
		(changed || selectors.length > 0);
	const deploymentId: string | null = url.searchParams.get('deployment') || null;
	const rawStart: string | null = url.searchParams.get('start');
	if (!rawStart || (selectors.length === 0 && !changed)) {
		return { selectors, changed, includeMissingUpstream, replayWindow: { mode: 'full' }, deploymentId };
	}
	const parsed: Date = parseUtc(rawStart);
	const replayWindow: ReplayWindow = Number.isFinite(parsed.getTime())
		? { mode: 'from', startTime: parsed.toISOString() }
		: { mode: 'full' };
	return { selectors, changed, includeMissingUpstream, replayWindow, deploymentId };
}

export function planLocationRequestKey(url: URL): string {
	const location: ParsedPlanLocation = readPlanLocation(url);
	const tokens: string[] = location.selectors.map(selectorToken);
	return `${tokens.join(',')}|${location.changed ? 'changed' : ''}|${location.includeMissingUpstream ? 'include-missing-upstream' : ''}|${replayStartToken(location.replayWindow) ?? ''}|${location.deploymentId ?? ''}`;
}

export function shouldClearReplayStart(url: URL): boolean {
	const rawStart: string | null = url.searchParams.get('start');
	if (rawStart === null) return false;
	const hasSelection: boolean = url.searchParams.get('changed') === '1' || url.searchParams
		.getAll('select')
		.some((token) => parseSelector(token) !== null);
	const parsed: Date = parseUtc(rawStart);
	return !hasSelection || !Number.isFinite(parsed.getTime());
}

export function writePlanSelection(
	url: URL,
	selectors: Selector[],
	replayWindow?: ReplayWindow,
	deploymentId: string | null = null,
	changed: boolean = false,
	includeMissingUpstream: boolean = false
): URL {
	const nextUrl: URL = new URL(url);
	nextUrl.searchParams.delete('select');
	nextUrl.searchParams.delete('deployment');
	nextUrl.searchParams.delete('changed');
	nextUrl.searchParams.delete('include_missing_upstream');
	if (changed) nextUrl.searchParams.set('changed', '1');
	else for (const selector of selectors) nextUrl.searchParams.append('select', selectorToken(selector));
	if (includeMissingUpstream) nextUrl.searchParams.set('include_missing_upstream', '1');
	if (replayWindow) {
		const start: string | null = replayStartToken(replayWindow);
		if (start === null) nextUrl.searchParams.delete('start');
		else nextUrl.searchParams.set('start', start);
	}
	if (deploymentId !== null) nextUrl.searchParams.set('deployment', deploymentId);
	return nextUrl;
}

export function writePlanDeployment(url: URL, deploymentId: string): URL {
	const nextUrl: URL = new URL(url);
	nextUrl.searchParams.set('deployment', deploymentId);
	return nextUrl;
}
