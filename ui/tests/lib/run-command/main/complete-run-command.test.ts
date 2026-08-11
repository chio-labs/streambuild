import { describe, expect, it } from 'vitest';

import { completeRunCommand } from '$lib/run-command/main/complete-run-command';
import type { RunCommandCompletion } from '$lib/run-command/types';

describe('complete run command', () => {
	it('given a cursor inside a quoted token when completing then the whole token is replaced and the suffix remains', () => {
		const command: string = `stb build --select "daily ord" --auto-approve`;
		const completion: RunCommandCompletion = completeRunCommand(
			command,
			command.indexOf('ord') + 3,
			"'daily orders'"
		);

		expect(completion).toEqual({
			command: "stb build --select 'daily orders' --auto-approve",
			cursor: 34
		});
	});
});
