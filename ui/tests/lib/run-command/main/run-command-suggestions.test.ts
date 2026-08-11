import { describe, expect, it } from 'vitest';

import type { Pipeline, Project } from '$lib/domain/types';
import { runCommandSuggestions } from '$lib/run-command/main/run-command-suggestions';
import type { RunCommandSuggestion } from '$lib/run-command/types';

const PROJECT: Project = {
	pipelines: [
		{ name: 'sales team', models: ['daily orders'] },
		{ name: 'inventory', models: ['stock'] }
	],
	models: [
		{ name: 'daily orders', pipeline: 'sales team' },
		{ name: 'stock', pipeline: 'inventory' }
	]
} as unknown as Project;

const PROTECTED_PIPELINES: Pipeline[] = [
	{
		name: 'sales team',
		protection: { confirmation: 'ship-it', warning: 'Protected' }
	} as Pipeline,
	{
		name: 'inventory',
		protection: { confirmation: 'ship-it', warning: 'Protected' }
	} as Pipeline
];

describe('run command suggestions', () => {
	it('given a partial selector when suggesting then matching pipeline and model values are shell quoted', () => {
		const command: string = 'stb build --select sales';
		const suggestions: RunCommandSuggestion[] = runCommandSuggestions(
			command,
			command.length,
			PROJECT,
			[]
		);

		expect(suggestions).toEqual([
			{
				value: "'pipeline:sales team'",
				primary: 'pipeline:sales team',
				secondary: '1 models',
				group: 'Pipelines'
			},
			{
				value: "'daily orders'",
				primary: 'daily orders',
				secondary: 'sales team',
				group: 'Models'
			}
		]);
	});

	it('given duplicate protected confirmations when suggesting then one unconfirmed value is offered', () => {
		const command: string = 'stb build --select stock --confirm ';
		const suggestions: RunCommandSuggestion[] = runCommandSuggestions(
			command,
			command.length,
			PROJECT,
			PROTECTED_PIPELINES
		);

		expect(suggestions).toEqual([
			{
				value: 'ship-it',
				primary: 'ship-it',
				secondary: 'sales team',
				group: 'Confirmations'
			}
		]);
	});

	it('given a partial flag when suggesting then only matching supported flags are offered', () => {
		const command: string = 'stb build --sta';
		const suggestions: RunCommandSuggestion[] = runCommandSuggestions(
			command,
			command.length,
			PROJECT,
			[]
		);

		expect(suggestions.map((suggestion) => suggestion.value)).toEqual(['--start-time']);
	});
});
