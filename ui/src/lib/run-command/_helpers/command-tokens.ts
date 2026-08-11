import { shellTokens } from '$lib/run-command/_helpers/shell-tokens';
import type {
	ActiveShellToken,
	RunCommandSuggestion,
	ShellToken
} from '$lib/run-command/types';

export function activeToken(raw: string, cursor: number): ActiveShellToken {
	const boundedCursor: number = Math.max(0, Math.min(cursor, raw.length));
	const tokens: ShellToken[] = shellTokens(raw, true).tokens;
	const current: ShellToken | undefined = tokens.find(
		(token) => boundedCursor >= token.start && boundedCursor <= token.end
	);
	const start: number = current?.start ?? boundedCursor;
	const end: number = current?.end ?? boundedCursor;
	const previous: ShellToken | undefined = tokens.filter((token) => token.end <= start).at(-1);
	const prefixTokens: ShellToken[] = shellTokens(raw.slice(start, boundedCursor), true).tokens;
	return {
		start,
		end,
		prefix: prefixTokens[0]?.value ?? '',
		previousToken: previous?.value ?? null
	};
}

export function collectFlagValues(raw: string, flag: string): string[] {
	const tokens: string[] = shellTokens(raw, true).tokens.map((token) => token.value);
	return tokens.flatMap((token, index) =>
		token === flag && tokens[index + 1] ? [tokens[index + 1]] : []
	);
}

export function filterSuggestions(
	options: RunCommandSuggestion[],
	needle: string
): RunCommandSuggestion[] {
	return options
		.filter(
			(option) =>
				needle === '' ||
				option.primary.toLowerCase().includes(needle) ||
				option.secondary.toLowerCase().includes(needle)
		)
		.slice(0, 12);
}
