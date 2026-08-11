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
	const selectors: Selector[] = url.searchParams
		.getAll('select')
		.map(parseSelector)
		.filter((selector): selector is Selector => selector !== null);
	const rawStart: string | null = url.searchParams.get('start');
	if (!rawStart || selectors.length === 0) return { selectors, replayWindow: { mode: 'full' } };
	const parsed: Date = parseUtc(rawStart);
	const replayWindow: ReplayWindow = Number.isFinite(parsed.getTime())
		? { mode: 'from', startTime: parsed.toISOString() }
		: { mode: 'full' };
	return { selectors, replayWindow };
}

export function shouldClearReplayStart(url: URL): boolean {
	const rawStart: string | null = url.searchParams.get('start');
	if (rawStart === null) return false;
	const hasSelector: boolean = url.searchParams
		.getAll('select')
		.some((token) => parseSelector(token) !== null);
	const parsed: Date = parseUtc(rawStart);
	return !hasSelector || !Number.isFinite(parsed.getTime());
}

export function writePlanSelection(
	url: URL,
	selectors: Selector[],
	replayWindow?: ReplayWindow
): URL {
	const nextUrl: URL = new URL(url);
	nextUrl.searchParams.delete('select');
	for (const selector of selectors) nextUrl.searchParams.append('select', selectorToken(selector));
	if (replayWindow) {
		const start: string | null = replayStartToken(replayWindow);
		if (start === null) nextUrl.searchParams.delete('start');
		else nextUrl.searchParams.set('start', start);
	}
	return nextUrl;
}
