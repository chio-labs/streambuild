import { parseSelector } from '$lib/planning/main/parse-selector';
import type { ParsedPlanCommand } from '$lib/plan-view/types';
import type { ReplayWindow, Selector } from '$lib/planning/types';

export function parsePlanCommand(command: string): ParsedPlanCommand {
	const tokens: string[] = command
		.replace(/^\s*(?:\$\s*)?(?:stb|streambuild)\s+(?:build|plan)\s*/, '')
		.split(/\s+/)
		.filter(Boolean);
	const selectors: Selector[] = [];
	let changed: boolean = false;
	let includeMissingUpstream: boolean = false;
	let start: string | null = null;
	let deploymentId: string | null = null;
	for (let index: number = 0; index < tokens.length; index += 1) {
		if (tokens[index] === '--changed') {
			changed = true;
		} else if (tokens[index] === '--include-missing-upstream') {
			includeMissingUpstream = true;
		} else if (tokens[index] === '--select' && tokens[index + 1] && !tokens[index + 1].startsWith('--')) {
			let next: number = index + 1;
			while (next < tokens.length && !tokens[next].startsWith('--')) {
				const parsed: Selector | null = parseSelector(tokens[next]);
				if (parsed) selectors.push(parsed);
				next += 1;
			}
			index = next - 1;
		} else if (tokens[index] === '--start-time' && tokens[index + 1]) {
			start = tokens[index + 1];
			index += 1;
		} else if (tokens[index] === '--deployment-id' && tokens[index + 1]) {
			deploymentId = tokens[index + 1];
			index += 1;
		}
	}
	if (changed && selectors.length > 0) {
		throw new Error('--changed cannot be combined with --select');
	}
	if (includeMissingUpstream && !changed && selectors.length === 0) {
		throw new Error('--include-missing-upstream requires --changed or --select');
	}
	let replayWindow: ReplayWindow = { mode: 'full' };
	if (start) {
		const parsedDate: Date = new Date(start.endsWith('Z') ? start : `${start}Z`);
		if (!Number.isNaN(parsedDate.getTime())) {
			replayWindow = { mode: 'from', startTime: parsedDate.toISOString() };
		}
	}
	return {
		selectors,
		changed,
		includeMissingUpstream,
		replayWindow,
		deploymentId
	};
}
