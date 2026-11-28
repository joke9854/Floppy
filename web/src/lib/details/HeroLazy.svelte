<script lang="ts">
	import { openTrack } from '#lib/track/open.svelte.ts';
	import RatingsGraph from './RatingsGraph.svelte';
	import SessionsDialog from './SessionsDialog.svelte';

	/**
	 * What the detail hero opens (P4-L3b): the activity sessions dialog for a
	 * `sessions_query`, or a ratings graph for a graph read. Loaded on the
	 * first tap, so the pages do not carry either dialog.
	 */
	let {
		query = '',
		graph = null,
		onclose
	}: {
		query?: string;
		graph?: { kind: 'provider' | 'trakt' | 'imdb'; url: string } | null;
		onclose: () => void;
	} = $props();

	let open = $state(true);
	$effect(() => {
		if (!open) onclose();
	});
</script>

{#if graph}
	<RatingsGraph bind:open kind={graph.kind} url={graph.url} />
{:else if query}
	<SessionsDialog
		bind:open
		{query}
		onedit={(target) => {
			open = false;
			openTrack(target);
		}}
	/>
{/if}
