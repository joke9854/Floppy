<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { Dialog } from 'bits-ui';
	import { t } from '#lib/strings.ts';

	/**
	 * The trailer player (ct/trailers.html): YouTube's player in a dialog,
	 * autoplaying; closing it (Escape, the backdrop, the button) stops it.
	 */
	let { key = $bindable(null) }: { key?: string | null } = $props();

	const open = $derived(key !== null);
</script>

<Dialog.Root open={open} onOpenChange={(next) => !next && (key = null)}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/80" />
		<Dialog.Content class="ct-trailer-player outline-none">
			<Dialog.Title class="sr-only">{t.trailer}</Dialog.Title>
			<Dialog.Close class="ct-trailer-player__close ct-glass-control" aria-label={t.close}>
				<X class="size-4" aria-hidden="true" />
			</Dialog.Close>
			{#if key}
				<iframe
					src={`https://www.youtube.com/embed/${encodeURIComponent(key)}?autoplay=1`}
					title={t.trailer}
					referrerpolicy="strict-origin-when-cross-origin"
					allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
					allowfullscreen
				></iframe>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
