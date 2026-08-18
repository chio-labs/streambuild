<script lang="ts">
	import { Dialog as DialogPrimitive } from "bits-ui";
	import type { ComponentProps } from "svelte";
	import DialogOverlay from "./dialog-overlay.svelte";
	import DialogPortal from "./dialog-portal.svelte";
	import { cn, type WithoutChildrenOrChild } from "$ui-kit/utils.js";

	let {
		ref = $bindable(null),
		class: className,
		portalProps,
		...restProps
	}: DialogPrimitive.ContentProps & {
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof DialogPortal>>;
	} = $props();
</script>

<DialogPortal {...portalProps}>
	<DialogOverlay />
	<DialogPrimitive.Content
		bind:ref
		data-slot="dialog-content"
		class={cn(
			"bg-popover text-popover-foreground data-open:animate-in data-closed:animate-out data-closed:fade-out-0 data-open:fade-in-0 data-closed:zoom-out-95 data-open:zoom-in-95 ring-foreground/10 fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[min(1200px,95vw)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-md shadow-lg ring-1 duration-100 outline-hidden",
			className
		)}
		{...restProps}
	/>
</DialogPortal>
