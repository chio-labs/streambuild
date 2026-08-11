import { activeToken } from '$lib/run-command/_helpers/command-tokens';
import type { ActiveShellToken, RunCommandCompletion } from '$lib/run-command/types';

export function completeRunCommand(
	raw: string,
	cursor: number,
	value: string
): RunCommandCompletion {
	const active: ActiveShellToken = activeToken(raw, cursor);
	const before: string = raw.slice(0, active.start);
	const after: string = raw.slice(active.end);
	const separator: string = /^\s/.test(after) ? '' : ' ';
	const command: string = `${before}${value}${separator}${after}`;
	return {
		command,
		cursor: before.length + value.length + (separator === '' ? 1 : separator.length)
	};
}
