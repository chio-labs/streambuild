import { shellTokens } from '$lib/run-command/_helpers/shell-tokens';
import { PINNED_CONTEXT_FLAGS } from '$lib/run-command/constants';
import type { ParsedRunCommand, ShellTokenization } from '$lib/run-command/types';

export function parseRunCommand(raw: string, target: string): ParsedRunCommand {
	const tokenized: ShellTokenization = shellTokens(raw);
	if (tokenized.error !== null) return commandError(tokenized.error);
	const tokens: string[] = tokenized.tokens.map((token) => token.value);
	if (tokens[0] !== 'stb' || tokens[1] !== 'build') {
		return commandError('command must start with `stb build`');
	}
	const selectors: string[] = [];
	const confirmations: string[] = [];
	let startTime: string | null = null;
	let index: number = 2;
	while (index < tokens.length) {
		const token: string = tokens[index];
		const pinnedFlag: string | undefined = PINNED_CONTEXT_FLAGS.find(
			(flag) => token === flag || token.startsWith(`${flag}=`)
		);
		if (pinnedFlag !== undefined) {
			return commandError(
				`${pinnedFlag} is fixed by stb dev and cannot be overridden from the UI (target ${target})`
			);
		}
		if (token === '--select' && tokens[index + 1]) {
			selectors.push(tokens[index + 1]);
			index += 2;
		} else if (token === '--start-time' && tokens[index + 1]) {
			startTime = tokens[index + 1];
			index += 2;
		} else if (token === '--confirm' && tokens[index + 1]) {
			confirmations.push(tokens[index + 1]);
			index += 2;
		} else if (token === '--auto-approve' || token === '--events') {
			index += 1;
		} else {
			return commandError(
				`unsupported token '${token}' - the UI accepts --select, --start-time, and --confirm`
			);
		}
	}
	if (startTime !== null && selectors.length === 0) {
		return commandError('--start-time requires --select');
	}
	return { selectors, startTime, confirmations, error: null };
}

function commandError(error: string): ParsedRunCommand {
	return { selectors: [], startTime: null, confirmations: [], error };
}
