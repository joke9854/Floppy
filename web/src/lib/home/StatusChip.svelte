<script lang="ts">
	import BookmarkPlus from '@lucide/svelte/icons/bookmark-plus';
	import CircleCheckBig from '@lucide/svelte/icons/circle-check-big';
	import OctagonX from '@lucide/svelte/icons/octagon-x';
	import Pause from '@lucide/svelte/icons/pause';
	import Play from '@lucide/svelte/icons/play';

	/**
	 * A poster card's status, as the Django status chip: the state's icon in
	 * its colour on a small glass pill over the poster's top-left corner.
	 */
	let { status }: { status: string } = $props();

	const STATES = {
		Completed: { icon: CircleCheckBig, color: 'text-emerald-400' },
		'In progress': { icon: Play, color: 'text-indigo-400' },
		Paused: { icon: Pause, color: 'text-orange-400' },
		Planning: { icon: BookmarkPlus, color: 'text-sky-400' },
		Dropped: { icon: OctagonX, color: 'text-red-400' }
	} as const;

	const state = $derived(STATES[status as keyof typeof STATES]);
</script>

{#if state}
	<span class="ct-status-chip" data-status={status} title={status}>
		<state.icon class="size-4 {state.color}" aria-hidden="true" />
		<span class="sr-only">{status}</span>
	</span>
{/if}
