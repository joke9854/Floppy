<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { trackRequest } from './open.svelte.ts';

	/**
	 * Where the track dialog lives (P4-D1): it loads on the first Track tap,
	 * so no page carries it. A save closes it, reloads the page's data and
	 * says what happened, as the Django page's toast does.
	 */
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function saved(message: string) {
		trackRequest.target = null;
		await invalidateAll();
		trackRequest.notice = message;
		clearTimeout(timer);
		timer = setTimeout(() => (trackRequest.notice = ''), 4000);
	}
</script>

{#if trackRequest.activity}
	{@const activity = trackRequest.activity}
	{#await import('./ActivityDialog.svelte') then { default: ActivityDialog }}
		<ActivityDialog
			target={activity}
			onclose={(changed) => {
				trackRequest.activity = null;
				if (changed) invalidateAll();
			}}
			onedit={(instanceId) => {
				// Copy the target first: clearing it re-reads `activity` as null.
				const from = { ...activity };
				trackRequest.activity = null;
				trackRequest.target = { ...from, instanceId };
			}}
		/>
	{/await}
{/if}
{#if trackRequest.target}
	{#await import('./TrackDialog.svelte') then { default: TrackDialog }}
		<TrackDialog target={trackRequest.target} onclose={() => (trackRequest.target = null)} onsaved={saved} />
	{/await}
{/if}
{#if trackRequest.notice}
	<p class="ct-track-notice" role="status">{trackRequest.notice}</p>
{/if}
