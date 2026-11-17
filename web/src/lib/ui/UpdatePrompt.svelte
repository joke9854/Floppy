<script lang="ts">
	import Button from './Button.svelte';

	/**
	 * Shown when a new version of the web app is out (`updated.current`).
	 * Reload lets the waiting service worker take over, then reloads; the
	 * page keeps working on the old version until then.
	 */
	let { visible, onreload }: { visible: boolean; onreload: () => void } = $props();
	let reloading = $state(false);
</script>

{#if visible}
	<div
		role="status"
		class="ct-glass fixed inset-x-3 bottom-[calc(96px+env(safe-area-inset-bottom))] z-50 flex items-center justify-between gap-3 rounded-ct-lg py-2.5 pr-2.5 pl-4 md:inset-x-auto md:right-4 md:bottom-4 md:w-[380px]"
	>
		<p class="text-sm font-semibold text-text">A new version of Floppy is ready.</p>
		<Button
			variant="primary"
			size="sm"
			disabled={reloading}
			onclick={() => {
				reloading = true;
				onreload();
			}}
		>
			Reload
		</Button>
	</div>
{/if}
