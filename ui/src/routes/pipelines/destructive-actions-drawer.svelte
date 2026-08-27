<script lang="ts">
	import ShieldAlertIcon from '@lucide/svelte/icons/shield-alert';
	import XIcon from '@lucide/svelte/icons/x';
	import * as Dialog from '$ui-kit/dialog/main';
	import Button from '$ui-kit/button/button.svelte';

	type Props = {
		open: boolean;
		selectedPipelineNames: string[];
		resetAllowed: boolean;
		target: string;
		database: string;
		onOpenChange: (open: boolean) => void;
		onReviewDestroy: () => void;
		onReviewReset: () => void;
	};

	let {
		open,
		selectedPipelineNames,
		resetAllowed,
		target,
		database,
		onOpenChange,
		onReviewDestroy,
		onReviewReset
	}: Props = $props();
</script>

<Dialog.Root {open} {onOpenChange}>
	<Dialog.Content
		class="data-closed:slide-out-to-right data-open:slide-in-from-right left-auto right-0 top-0 h-dvh max-h-none w-full max-w-[480px] translate-x-0 translate-y-0 rounded-none border-l border-border"
		data-testid="destructive-actions-drawer"
	>
		<Dialog.Header class="shrink-0 border-b border-border px-4 py-4 sm:px-5">
			<div class="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-destructive/10 text-destructive">
				<ShieldAlertIcon size={18} />
			</div>
			<div class="min-w-0 flex-1">
				<Dialog.Title class="font-display text-[17px] font-semibold">Destructive actions</Dialog.Title>
				<Dialog.Description class="mt-1 text-[11.5px]">
					Planning is read-only. Execution still requires review and confirmation.
				</Dialog.Description>
			</div>
			<Dialog.Close
				class="text-muted-foreground hover:text-foreground grid h-8 w-8 place-items-center rounded-md hover:bg-muted"
				aria-label="Close destructive actions"
			>
				<XIcon size={15} />
			</Dialog.Close>
		</Dialog.Header>

		<div class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
			<p class="text-muted-foreground text-[12px] leading-relaxed">
				These operations remove warehouse resources and may interrupt active pipelines. You will
				review the complete dependency plan before anything is executed.
			</p>

			<section class="mt-5" aria-labelledby="selected-pipelines-actions">
				<div class="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--sb-text-faint)]">
					Selected pipelines
				</div>
				<h3 id="selected-pipelines-actions" class="mt-1 font-display text-[15px] font-semibold">
					{selectedPipelineNames.length} {selectedPipelineNames.length === 1 ? 'pipeline' : 'pipelines'} selected
				</h3>
				<p class="text-muted-foreground mt-1 text-[11.5px]">
					Destroy only the selected pipelines and any dependants you explicitly approve in the review flow.
				</p>
				{#if selectedPipelineNames.length > 0}
					<div class="mt-3 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
						{#each selectedPipelineNames as name (name)}
							<code class="rounded border border-border bg-[var(--sb-inset)] px-2 py-1 text-[10px]">{name}</code>
						{/each}
					</div>
				{/if}
				<Button
					variant="destructive"
					class="mt-4 w-full font-mono text-[11px]"
					disabled={selectedPipelineNames.length === 0}
					title={selectedPipelineNames.length === 0 ? 'Select pipelines you have permission to destroy' : undefined}
					onclick={onReviewDestroy}
				>
					Review destroy plan
				</Button>
			</section>

			<div class="my-6 border-t border-[var(--border-subtle)]"></div>

			<section aria-labelledby="entire-target-actions">
				<div class="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--sb-text-faint)]">
					Entire target
				</div>
				<h3 id="entire-target-actions" class="mt-1 font-display text-[15px] font-semibold">
					Reset {target} / {database}
				</h3>
				<p class="text-muted-foreground mt-1 text-[11.5px]">
					Remove all StreamBuild-managed resources in this target, regardless of the current pipeline selection.
				</p>
				<Button
					variant="destructive"
					class="mt-4 w-full font-mono text-[11px]"
					disabled={!resetAllowed}
					title={resetAllowed ? 'Review a reset of the entire target' : 'Requires the target.reset permission'}
					onclick={onReviewReset}
				>
					Review target reset
				</Button>
			</section>
		</div>
	</Dialog.Content>
</Dialog.Root>
