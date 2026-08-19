import { describe, expect, it } from 'vitest';

import { parseRunCommand } from '$lib/run-command/main/parse-run-command';
import type { ParsedRunCommand } from '$lib/run-command/types';

describe('parse run command', () => {
	it('given quoted and escaped values when parsing a build command then shell tokens are preserved', () => {
		const parsed: ParsedRunCommand = parseRunCommand(
			`stb build --select 'daily orders' --select customer\\ events --start-time "2026-08-11T09:00:00Z" --confirm 'ship it'`,
			'dev'
		);

		expect(parsed).toEqual({
			selectors: ['daily orders', 'customer events'],
			startTime: '2026-08-11T09:00:00Z',
			confirmations: ['ship it'],
			error: null
		});
	});

	it('given one --select flag with several space-separated names when parsing then all names become selectors', () => {
		const parsed: ParsedRunCommand = parseRunCommand(
			'stb build --select alpha beta gamma --auto-approve',
			'dev'
		);

		expect(parsed).toEqual({
			selectors: ['alpha', 'beta', 'gamma'],
			startTime: null,
			confirmations: [],
			error: null
		});
	});

	it('given a pinned target override when parsing then the UI rejects the command for its dev target', () => {
		const parsed: ParsedRunCommand = parseRunCommand('stb build --target=prod', 'local');

		expect(parsed).toEqual({
			selectors: [],
			startTime: null,
			confirmations: [],
			error: '--target is fixed by stb dev and cannot be overridden from the UI (target local)'
		});
	});

	it('given an unterminated quote when parsing then a shell syntax error is returned', () => {
		const parsed: ParsedRunCommand = parseRunCommand("stb build --select 'daily orders", 'dev');

		expect(parsed.error).toBe('command contains an unterminated quote or escape');
	});
});
