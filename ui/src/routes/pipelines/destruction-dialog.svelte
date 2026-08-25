<script lang="ts">
	import XIcon from '@lucide/svelte/icons/x';
	import ShieldAlertIcon from '@lucide/svelte/icons/shield-alert';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import * as Dialog from '$ui-kit/dialog/main';
	import Button from '$ui-kit/button/button.svelte';
	import { destructionOperationLabel } from '$lib/pipeline-view/main/destruction-operation-label';
	import type { DestructionController } from './types';

	type Props = {
		state: DestructionController;
		dependentPermissionsAvailable: boolean;
	};

	let { state, dependentPermissionsAvailable }: Props = $props();
</script>

<Dialog.Root open={state.open} onOpenChange={(open) => state.setOpen(open)}>
	<Dialog.Content class="w-[min(1040px,96vw)]">
		<Dialog.Header class="shrink-0">
			<div class="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-destructive/10 text-destructive">
				<ShieldAlertIcon size={17} />
			</div>
			<div class="min-w-0 flex-1">
				<Dialog.Title class="font-display text-[16px] font-semibold">
					{state.operation === null ? 'Destruction plan' : destructionOperationLabel(state.operation)}
				</Dialog.Title>
				<Dialog.Description class="mt-1 font-mono">
					Planning is read-only. Valid plans open on a dedicated review page.
				</Dialog.Description>
			</div>
			<Dialog.Close
				class="text-muted-foreground hover:text-foreground grid h-8 w-8 place-items-center rounded-md hover:bg-muted disabled:opacity-50"
				disabled={state.planning}
				aria-label="Close destruction plan"
			>
				<XIcon size={15} />
			</Dialog.Close>
		</Dialog.Header>

		<div class="min-h-0 flex-1 overflow-y-auto">
			{#if state.planning}
				<div class="grid min-h-[360px] place-items-center px-6 text-center">
					<div>
						<div class="mx-auto mb-3 h-5 w-5 animate-spin rounded-full border-2 border-border border-t-destructive"></div>
						<div class="font-display text-[14px] font-medium">Inspecting the warehouse</div>
						<p class="text-muted-foreground mt-1 font-mono text-[10.5px]">No mutation occurs while planning.</p>
					</div>
				</div>
			{:else if state.plan !== null && state.plan.blocked}
				{@const plan = state.plan}
				<div class="p-4 sm:p-5">
					<section class="rounded-md border border-destructive/40 bg-destructive/5 p-4" aria-labelledby="closure-heading">
						<div class="flex items-start gap-3">
							<TriangleAlertIcon size={16} class="mt-0.5 shrink-0 text-destructive" />
							<div class="min-w-0 flex-1">
								<h3 id="closure-heading" class="text-[13px] font-semibold text-destructive">Dependency closure is incomplete</h3>
								<p class="text-muted-foreground mt-1 text-[11.5px]">These dependent or shared-source pipelines were not silently included. Confirm their inclusion before opening the frozen review page.</p>
								<div class="mt-3 flex flex-wrap gap-1.5">
									{#each plan.requiredDependentPipelines as pipeline (pipeline)}
										<code class="rounded border border-destructive/20 bg-background px-2 py-1 text-[10.5px]">{pipeline}</code>
									{/each}
								</div>
								<Button
									variant="destructive"
									size="sm"
									class="mt-3 font-mono text-[11px]"
									disabled={!dependentPermissionsAvailable}
									title={dependentPermissionsAvailable ? undefined : 'Requires pipeline.destroy permission for every required dependent pipeline'}
									onclick={() => void state.addRequiredDependentsAndReplan()}
								>
									Select required pipelines and open review
								</Button>
								{#if !dependentPermissionsAvailable}
									<p class="mt-2 font-mono text-[10.5px] text-destructive">You do not have pipeline.destroy permission for every required dependent pipeline.</p>
								{/if}
							</div>
						</div>
					</section>
				</div>
			{/if}

			{#if state.error !== null}
				<div class="m-4 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2.5 font-mono text-[11px] text-destructive" role="alert">
					{state.error}
				</div>
			{/if}
		</div>
	</Dialog.Content>
</Dialog.Root>
