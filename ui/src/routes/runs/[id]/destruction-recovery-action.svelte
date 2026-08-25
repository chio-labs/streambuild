<script lang="ts">
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';
	import { createDestructionRecoveryPlan } from '$lib/api/main/destruction/create-destruction-recovery-plan';
	import type { DestructionOperation, DestructionPlan } from '$lib/pipeline-view/types';
	import { destructionRecoveryOperation } from '$lib/run-presentation/main/destruction-recovery-operation';

	type Props = {
		invocationId: string;
		outcome: string;
		command: string | null;
		onPlanCreated: (planId: string) => Promise<void>;
	};

	let { invocationId, outcome, command, onPlanCreated }: Props = $props();
	let planning = $state<boolean>(false);
	let error = $state<string | null>(null);
	const operation: DestructionOperation | null = $derived(
		destructionRecoveryOperation(outcome, command)
	);

	async function createRecovery(): Promise<void> {
		planning = true;
		error = null;
		try {
			const plan: DestructionPlan = await createDestructionRecoveryPlan(invocationId);
			await onPlanCreated(plan.planId);
		} catch (caught) {
			error = caught instanceof Error ? caught.message : String(caught);
		} finally {
			planning = false;
		}
	}
</script>

{#if operation !== null}
	<button
		class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded border border-border px-2.5 py-1 font-mono text-[10.5px]"
		disabled={planning}
		onclick={() => void createRecovery()}
	>
		<RotateCcwIcon size={11} /> {planning ? 'Creating recovery plan…' : 'Create recovery plan'}
	</button>
	{#if error !== null}
		<span class="max-w-sm font-mono text-[10.5px] text-destructive" role="alert">{error}</span>
	{/if}
{/if}
