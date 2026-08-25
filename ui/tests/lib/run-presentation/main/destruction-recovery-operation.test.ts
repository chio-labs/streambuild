import { describe, expect, it } from 'vitest';

import { destructionRecoveryOperation } from '$lib/run-presentation/main/destruction-recovery-operation';

interface DestructionRecoveryOperationTestCase {
	readonly description: string;
	readonly outcome: string;
	readonly command: string;
	readonly mode: string;
	readonly expectedOperation: 'destroy_pipelines' | 'reset_target' | null;
}

describe('destruction recovery operation', () => {
	it.each<DestructionRecoveryOperationTestCase>([
		{
			description: 'failed pipeline destruction is recoverable',
			outcome: 'failed',
			command: 'destroy pipelines',
			mode: 'destructive',
			expectedOperation: 'destroy_pipelines'
		},
		{
			description: 'failed target reset is recoverable',
			outcome: 'failed',
			command: 'reset target',
			mode: 'destructive',
			expectedOperation: 'reset_target'
		},
		{
			description: 'successful destruction is not recoverable',
			outcome: 'succeeded',
			command: 'destroy pipelines',
			mode: 'destructive',
			expectedOperation: null
		},
		{
			description: 'presumed failure is not terminal recovery evidence',
			outcome: 'presumed_failed',
			command: 'destroy pipelines',
			mode: 'destructive',
			expectedOperation: null
		},
		{
			description: 'failed non-destruction command is not recoverable',
			outcome: 'failed',
			command: 'build',
			mode: 'destructive',
			expectedOperation: null
		},
		{
			description: 'failed non-destructive mode is not recoverable',
			outcome: 'failed',
			command: 'destroy pipelines',
			mode: 'interactive',
			expectedOperation: null
		}
	])('$description', (testCase: DestructionRecoveryOperationTestCase) => {
		expect(destructionRecoveryOperation(testCase.outcome, testCase.command, testCase.mode)).toBe(
			testCase.expectedOperation
		);
	});
});
