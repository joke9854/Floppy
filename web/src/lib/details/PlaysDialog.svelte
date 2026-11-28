<script lang="ts">
	import './media.css';
	import { djangoWrite } from '#lib/csrf.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { dt } from './strings.ts';
	import { playTime, toIsoWithOffset, toLocalInput, type MediaPlay } from './media.ts';

	/**
	 * The plays of one song or podcast episode (the page's fill_track_song.html
	 * dialog): each play with Delete, and Add play with a date and time
	 * (default now, optionally the release or publish date). Deleting sends the
	 * play's history id; adding posts the exact instant chosen, with its
	 * offset. The page reloads its data when the dialog closes after a change.
	 */
	let {
		open = $bindable(false),
		title,
		kind,
		plays,
		suggestion = null,
		body,
		onchange
	}: {
		open?: boolean;
		title: string;
		kind: 'music' | 'podcast';
		plays: MediaPlay[];
		/** A "Release date" or "Published" shortcut: its label and the local date and time it fills. */
		suggestion?: { label: string; local: string } | null;
		/** The play's target fields (the add request's body, without `end_date`). */
		body: Record<string, number | string | null>;
		onchange: () => void;
	} = $props();

	const addPath = $derived(
		kind === 'music' ? '/api/v1/music/songs/plays/' : '/api/v1/podcasts/episodes/plays/'
	);

	let removed = $state<number[]>([]);
	let local = $state(toLocalInput(new Date()));
	let busy = $state(false);
	let problem = $state('');
	let changed = false;
	const shown = $derived(plays.filter((play) => !removed.includes(play.history_id)));

	$effect(() => {
		if (open) {
			removed = [];
			local = toLocalInput(new Date());
			problem = '';
			changed = false;
		} else if (changed) {
			changed = false;
			onchange();
		}
	});

	async function remove(play: MediaPlay) {
		if (busy || !confirm(dt.deleteConfirm)) return;
		busy = true;
		problem = '';
		try {
			const response = await djangoWrite(`/api/v1/history/${kind}/${play.history_id}/`, 'DELETE');
			if (!response.ok) throw new Error(String(response.status));
			removed = [...removed, play.history_id];
			changed = true;
		} catch {
			problem = dt.playDeleteFailed;
		} finally {
			busy = false;
		}
	}

	async function add(event: SubmitEvent) {
		event.preventDefault();
		const endDate = toIsoWithOffset(local);
		if (busy || !endDate) return;
		busy = true;
		problem = '';
		try {
			const response = await djangoWrite(addPath, 'POST', { ...body, end_date: endDate });
			if (!response.ok) throw new Error(String(response.status));
			changed = true;
			open = false;
		} catch {
			problem = dt.playSaveFailed;
		} finally {
			busy = false;
		}
	}
</script>

<Dialog bind:open title={dt.playsOf(title)} sheet>
	<div class="ct-plays-dialog">
		{#if shown.length}
			<ul class="ct-plays-dialog__list">
				{#each shown as play (play.history_id)}
					<li class="ct-plays-dialog__item">
						<time datetime={play.end_date}>{playTime(play.end_date)}</time>
						<button
							type="button"
							class="ct-plays-dialog__delete"
							aria-label={dt.deletePlay(playTime(play.end_date))}
							disabled={busy}
							onclick={() => remove(play)}
						>
							{dt.delete}
						</button>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="ct-plays-dialog__empty">{dt.noPlays}</p>
		{/if}

		<form class="ct-plays-dialog__form" onsubmit={add}>
			<label class="ct-plays-dialog__label" for="ct-play-at">{dt.playedAt}</label>
			<input
				id="ct-play-at"
				class="ct-plays-dialog__input"
				type="datetime-local"
				step="1"
				bind:value={local}
				required
			/>
			<div class="ct-plays-dialog__chips">
				<button type="button" onclick={() => (local = toLocalInput(new Date()))}>{dt.now}</button>
				{#if suggestion}
					<button type="button" onclick={() => (local = suggestion.local)}>{suggestion.label}</button>
				{/if}
			</div>
			{#if problem}<p class="ct-detail-problem" role="alert">{problem}</p>{/if}
			<button type="submit" class="ct-btn-primary" disabled={busy || !local}>{dt.addPlay}</button>
		</form>
	</div>
</Dialog>
