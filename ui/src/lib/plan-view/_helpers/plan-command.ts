import { parseSelector } from '$lib/planning/main/parse-selector';
import type { ParsedPlanCommand } from '$lib/plan-view/types';
import type { ReplayWindow, Selector } from '$lib/planning/types';

export function parsePlanCommand(command: string): ParsedPlanCommand {
	const tokens: string[] = command
		.replace(/^\s*(?:\$\s*)?(?:stb|streambuild)\s+(?:build|plan)\s*/, '')
		.split(/\s+/)
		.filter(Boolean);
	const selectors: Selector[] = [];
	let start: string | null = null;
	for (let index: number = 0; index < tokens.length; index += 1) {
		if (tokens[index] === '--select' && tokens[index + 1]) {
			const parsed: Selector | null = parseSelector(tokens[index + 1]);
			if (parsed) selectors.push(parsed);
			index += 1;
		} else if (tokens[index] === '--start-time' && tokens[index + 1]) {
			start = tokens[index + 1];
			index += 1;
		}
	}
	let replayWindow: ReplayWindow = { mode: 'full' };
	if (start) {
		const parsedDate: Date = new Date(start.endsWith('Z') ? start : `${start}Z`);
		if (!Number.isNaN(parsedDate.getTime())) {
			replayWindow = { mode: 'from', startTime: parsedDate.toISOString() };
		}
	}
	return { selectors, replayWindow };
}
