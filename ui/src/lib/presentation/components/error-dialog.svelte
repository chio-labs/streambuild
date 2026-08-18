<script lang="ts">
	import XIcon from '@lucide/svelte/icons/x';
	import * as Dialog from '$ui-kit/dialog/main';
	import ErrorView from './error-view.svelte';

	type Props = {
		open?: boolean;
		text: string;
		title?: string;
		subtitle?: string;
	};
	let { open = $bindable(false), text, title = 'Error', subtitle }: Props = $props();
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="w-auto min-w-[min(560px,92vw)] max-w-[80vw]">
		<Dialog.Header>
			<div class="min-w-0 flex-1">
				<Dialog.Title class="text-[13px] font-medium text-[color:var(--sb-error)]"
					>{title}</Dialog.Title
				>
				{#if subtitle}
					<Dialog.Description class="truncate pt-0.5 font-mono" title={subtitle}
						>{subtitle}</Dialog.Description
					>
				{/if}
			</div>
			<Dialog.Close
				class="text-muted-foreground hover:text-foreground shrink-0 rounded p-1"
				aria-label="Close"
			>
				<XIcon size={15} />
			</Dialog.Close>
		</Dialog.Header>
		<div class="flex min-h-0 flex-1 flex-col overflow-hidden p-3">
			<ErrorView {text} maxHeight="80vh" />
		</div>
	</Dialog.Content>
</Dialog.Root>
