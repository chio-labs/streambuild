<script lang="ts">
	import XIcon from '@lucide/svelte/icons/x';
	import ShieldAlertIcon from '@lucide/svelte/icons/shield-alert';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import * as Dialog from '$ui-kit/dialog/main';
	import Button from '$ui-kit/button/button.svelte';
	import type { DestructionExecution } from '$lib/pipeline-view/types';
	import { formatBytes } from '$lib/formatting/main/format-bytes';
	import { destructionOperationLabel, formatPlanTimestamp } from './destruction-presentation';
	import type { DestructionController } from './types';

	type Props = {
		state: DestructionController;
		dependentPermissionsAvailable: boolean;
		onExecuted(result: DestructionExecution): void;
	};

	let { state, dependentPermissionsAvailable, onExecuted }: Props = $props();

	async function execute(): Promise<void> {
		const result: DestructionExecution | null = await state.execute();
		if (result !== null) onExecuted(result);
	}

	function displayBytes(bytes: number): string {
		return bytes === 0 ? '0 B' : formatBytes(bytes);
	}
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
					Frozen warehouse impact review. Closing this dialog does not execute anything.
				</Dialog.Description>
			</div>
			<Dialog.Close
				class="text-muted-foreground hover:text-foreground grid h-8 w-8 place-items-center rounded-md hover:bg-muted disabled:opacity-50"
				disabled={state.planning || state.reviewing || state.executing}
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
			{:else if state.plan !== null}
				{@const plan = state.plan}
				<div class="grid gap-4 p-4 sm:p-5">
					<section class="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4" aria-label="Plan identity">
						<div class="bg-popover p-3">
							<div class="text-[var(--sb-text-faint)] font-mono text-[9px] uppercase tracking-[0.14em]">Operation</div>
							<div class="mt-1 text-[12.5px] font-medium text-destructive">{destructionOperationLabel(plan.operation)}</div>
						</div>
						<div class="bg-popover p-3">
							<div class="text-[var(--sb-text-faint)] font-mono text-[9px] uppercase tracking-[0.14em]">Target</div>
							<div class="mt-1 font-mono text-[12px]">{plan.target}</div>
						</div>
						<div class="bg-popover p-3">
							<div class="text-[var(--sb-text-faint)] font-mono text-[9px] uppercase tracking-[0.14em]">Database</div>
							<div class="mt-1 truncate font-mono text-[12px]" title={plan.database}>{plan.database}</div>
						</div>
						<div class="bg-popover p-3">
							<div class="text-[var(--sb-text-faint)] font-mono text-[9px] uppercase tracking-[0.14em]">Estimated storage</div>
							<div class="mt-1 font-mono text-[12px]">{displayBytes(plan.estimatedBytes)}</div>
						</div>
					</section>

					{#if plan.blocked}
						<section class="rounded-md border border-destructive/40 bg-destructive/5 p-4" aria-labelledby="closure-heading">
							<div class="flex items-start gap-3">
								<TriangleAlertIcon size={16} class="mt-0.5 shrink-0 text-destructive" />
								<div class="min-w-0 flex-1">
									<h3 id="closure-heading" class="text-[13px] font-semibold text-destructive">Dependency closure is incomplete</h3>
									<p class="text-muted-foreground mt-1 text-[11.5px]">These downstream pipelines depend on the selection. They were not silently included, and this plan cannot be reviewed or executed.</p>
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
										Select required pipelines and replan
									</Button>
									{#if !dependentPermissionsAvailable}
										<p class="mt-2 font-mono text-[10.5px] text-destructive">You do not have pipeline.destroy permission for every required dependent pipeline.</p>
									{/if}
								</div>
							</div>
						</section>
					{/if}

					<section aria-labelledby="closure-impact-heading">
						<div class="mb-2 flex items-baseline justify-between gap-3">
							<h3 id="closure-impact-heading" class="font-display text-[13px] font-semibold">Frozen pipeline closure</h3>
							<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">{plan.affectedPipelines.length} affected</span>
						</div>
						<div class="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-2">
							<div>
								<div class="text-[var(--sb-text-faint)] font-mono text-[9px] uppercase tracking-[0.13em]">Selected</div>
								<div class="mt-1.5 flex flex-wrap gap-1">
									{#each plan.selectedPipelines as pipeline (pipeline)}
										<code class="rounded bg-muted px-1.5 py-0.5 text-[10.5px]">{pipeline}</code>
									{:else}
										<span class="text-muted-foreground text-[11px]">Entire target</span>
									{/each}
								</div>
							</div>
							<div>
								<div class="text-[var(--sb-text-faint)] font-mono text-[9px] uppercase tracking-[0.13em]">Affected</div>
								<div class="mt-1.5 flex flex-wrap gap-1">
									{#each plan.affectedPipelines as pipeline (pipeline)}
										<code class="rounded bg-destructive/10 px-1.5 py-0.5 text-[10.5px] text-destructive">{pipeline}</code>
									{/each}
								</div>
							</div>
						</div>
					</section>

					<section class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(270px,0.42fr)]" aria-label="Affected models and retention policy">
						<div class="rounded-md border border-border p-3">
							<div class="flex items-baseline justify-between gap-2">
								<h3 class="font-display text-[13px] font-semibold">Models</h3>
								<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">{plan.models.length}</span>
							</div>
							<div class="mt-2 flex max-h-28 flex-wrap content-start gap-1 overflow-y-auto">
								{#each plan.models as model (model)}
									<code class="rounded bg-muted px-1.5 py-0.5 text-[10.5px]">{model}</code>
								{:else}
									<span class="text-muted-foreground text-[11px]">No models are present in this plan.</span>
								{/each}
							</div>
						</div>
						<div class="rounded-md border border-border p-3">
							<h3 class="font-display text-[13px] font-semibold">Data policy</h3>
							<dl class="mt-2 grid gap-2 text-[11px]">
								<div class="flex items-center justify-between gap-3"><dt class="text-muted-foreground">Managed sources</dt><dd class:!text-destructive={plan.managedSourcesIncluded} class="font-mono">{plan.managedSourcesIncluded ? 'included' : 'preserved'}</dd></div>
								<div class="flex items-center justify-between gap-3"><dt class="text-muted-foreground">Retained replay data</dt><dd class:!text-destructive={plan.retainedReplayDataIncluded} class="font-mono">{plan.retainedReplayDataIncluded ? 'included' : 'preserved'}</dd></div>
							</dl>
						</div>
					</section>

					<section aria-labelledby="resources-heading">
						<div class="mb-2 flex items-baseline justify-between gap-3">
							<h3 id="resources-heading" class="font-display text-[13px] font-semibold">Physical resources</h3>
							<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">{plan.resources.length} recorded</span>
						</div>
						<div class="max-h-56 overflow-auto rounded-md border border-border">
							<table class="sb-list w-full min-w-[720px] text-left text-[11px]">
								<caption class="sr-only">Frozen physical resources affected by this destruction plan</caption>
								<thead class="sticky top-0 z-10 font-mono text-[9px] uppercase tracking-[0.12em] text-[var(--sb-text-faint)]">
									<tr><th class="px-3 py-2 font-normal">Resource</th><th class="px-3 py-2 font-normal">Kind</th><th class="px-3 py-2 font-normal">Logical / pipeline</th><th class="px-3 py-2 text-right font-normal">Bytes</th><th class="px-3 py-2 text-right font-normal">Parts</th><th class="px-3 py-2 font-normal">State</th></tr>
								</thead>
								<tbody>
									{#each plan.resources as resource (`${resource.kind}:${resource.name}`)}
										<tr>
											<td class="px-3 py-2 font-mono">{resource.name}</td>
											<td class="px-3 py-2 font-mono text-muted-foreground">{resource.kind.replaceAll('_', ' ')}</td>
											<td class="px-3 py-2"><div class="font-mono">{resource.logicalName}</div><div class="text-[var(--sb-text-faint)] text-[10px]">{resource.pipelineName ?? 'target source'}</div></td>
											<td class="px-3 py-2 text-right font-mono">{resource.bytes === null ? 'unknown' : displayBytes(resource.bytes)}</td>
											<td class="px-3 py-2 text-right font-mono">{resource.activeParts ?? '—'}</td>
											<td class="px-3 py-2"><span class="sb-tag font-mono" class:text-destructive={resource.exists}>{resource.exists ? 'exists' : 'absent'}</span></td>
										</tr>
									{:else}
										<tr><td colspan="6" class="px-3 py-5 text-center text-muted-foreground">No owned physical resources were found.</td></tr>
									{/each}
								</tbody>
							</table>
						</div>
					</section>

					<section class="rounded-md border border-destructive/30 bg-destructive/5 p-4" aria-labelledby="irreversible-heading">
						<div class="flex gap-3">
							<ShieldAlertIcon size={16} class="mt-0.5 shrink-0 text-destructive" />
							<div>
								<h3 id="irreversible-heading" class="text-[13px] font-semibold text-destructive">This operation is irreversible</h3>
								<p class="mt-1 text-[11.5px] leading-relaxed">Execution permanently drops the resources listed above from <code>{plan.database}</code>. StreamBuild does not provide rollback for destruction operations.</p>
								<p class="mt-2 text-[11.5px] leading-relaxed">Authored project definitions remain. A later build can recreate resources still defined in the project, but it cannot restore their dropped data.</p>
							</div>
						</div>
					</section>

					<section class="rounded-md border border-border bg-[var(--sb-surface-low)] p-4" aria-labelledby="authorization-heading">
						<div class="flex flex-wrap items-start justify-between gap-3">
							<div>
								<h3 id="authorization-heading" class="font-display text-[13px] font-semibold">{state.reviewed ? 'Gate 2 · Exact challenges' : 'Gate 1 · Review frozen plan'}</h3>
								<p class="text-muted-foreground mt-1 text-[11px]">Plan <code>{plan.planId}</code> expires {formatPlanTimestamp(plan.expiresAt)}.</p>
							</div>
							<code class="max-w-full break-all text-right text-[9.5px] text-[var(--sb-text-faint)]" title="Plan fingerprint">{plan.planFingerprint}</code>
						</div>

						{#if !plan.blocked && !state.reviewed}
							<p class="mt-3 text-[11.5px]">Review records that this exact frozen impact was presented. It does not authorize execution.</p>
							<Button variant="outline" size="sm" class="mt-3 font-mono text-[11px]" disabled={state.reviewing} onclick={() => void state.review()}>
								{state.reviewing ? 'Recording review…' : 'Review frozen plan'}
							</Button>
						{:else if state.reviewed}
							<p class="mt-3 text-[11.5px]">Type each value exactly as shown. Values are case-sensitive and are sent separately without trimming or normalization.</p>
							<div class="mt-3 grid gap-3 sm:grid-cols-2">
								{#each plan.challengeValues as challenge, index (`${index}:${challenge}`)}
									<label class="grid gap-1.5" for="destruction-challenge-{index}">
										<span class="text-[10.5px]">Challenge {index + 1}: <code class="select-all text-destructive">{challenge}</code></span>
										<input
											id="destruction-challenge-{index}"
											type="text"
											value={state.responses[index] ?? ''}
											autocomplete="off"
											spellcheck="false"
											class="h-9 rounded-md border border-input bg-background px-2.5 font-mono text-[12px] outline-none focus:border-ring focus:ring-2 focus:ring-ring/30"
											oninput={(event) => state.setResponse(index, event.currentTarget.value)}
										/>
									</label>
								{/each}
							</div>
							<Button variant="destructive" class="mt-4 w-full font-mono text-[11px]" disabled={!state.canExecute || state.executing} onclick={() => void execute()}>
								{state.executing ? 'Executing irreversible operation…' : destructionOperationLabel(plan.operation)}
							</Button>
						{/if}
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
