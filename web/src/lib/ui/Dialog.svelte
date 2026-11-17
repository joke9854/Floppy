<script lang="ts">
	import { Dialog } from 'bits-ui';
	import type { Snippet } from 'svelte';

	/**
	 * A centred dialog (bits-ui: focus trap, Escape, scroll lock). `sheet`
	 * makes it a bottom sheet on phones, as CineTrack's sheets.
	 */
	let {
		open = $bindable(false),
		title,
		description = '',
		sheet = false,
		children
	}: {
		open?: boolean;
		title: string;
		description?: string;
		sheet?: boolean;
		children: Snippet;
	} = $props();
</script>

<Dialog.Root bind:open>
	<Dialog.Portal>
		<Dialog.Overlay
			class="fixed inset-0 z-50 bg-black/55"
		/>
		<Dialog.Content
			class="ct-glass fixed z-50 flex max-h-[85dvh] flex-col gap-4 overflow-y-auto p-6 outline-none {sheet
				? 'inset-x-3 bottom-[calc(10px+env(safe-area-inset-bottom))] rounded-ct-lg md:inset-x-auto md:bottom-auto md:left-1/2 md:top-1/2 md:w-[420px] md:-translate-x-1/2 md:-translate-y-1/2'
				: 'left-1/2 top-1/2 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 rounded-ct-lg'}"
		>
			<Dialog.Title class="text-lg font-bold text-text">{title}</Dialog.Title>
			{#if description}
				<Dialog.Description class="text-sm text-muted">{description}</Dialog.Description>
			{/if}
			{@render children()}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
