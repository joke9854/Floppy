<script lang="ts">
	import { STATUS_LOOKS } from '#lib/media/status.ts';

	/**
	 * A poster card's status, as the Django status chip: the state's icon in
	 * its colour on a small glass pill over the poster's top-left corner.
	 */
	let { status }: { status: string } = $props();

	const state = $derived(STATUS_LOOKS[status]);
</script>

{#if state}
	<span class="ct-status-chip" data-status={status} title={status}>
		<state.icon class="size-4 {state.color}" aria-hidden="true" />
		<span class="sr-only">{status}</span>
	</span>
{/if}
