import type { RunCommandFlag } from '$lib/run-command/types';

export const RUN_COMMAND_FLAGS: RunCommandFlag[] = [
	{ flag: '--select', hint: '<name…>', description: 'Limit the rebuild scope (space-separated)' },
	{
		flag: '--start-time',
		hint: '<YYYY-MM-DDTHH:MM:SSZ>',
		description: 'Bound the replay window'
	},
	{ flag: '--confirm', hint: '<word>', description: 'Confirm a protected pipeline' }
];

export const PINNED_CONTEXT_FLAGS: string[] = [
	'--project-dir',
	'--target',
	'--vars',
	'--host',
	'--port',
	'--username',
	'--password',
	'--database'
];
