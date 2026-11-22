<script lang="ts">
	import Pencil from '@lucide/svelte/icons/pencil';
	import Trash from '@lucide/svelte/icons/trash-2';
	import X from '@lucide/svelte/icons/x';
	import { Dialog } from 'bits-ui';
	import type { components } from '#lib/api/client.ts';
	import { csrfToken } from '#lib/csrf.ts';
	import { t } from '#lib/strings.ts';
	import type { TrackTarget } from './open.svelte.ts';
	import { tt } from './strings.ts';
	import './track.css';

	type Activity = components['schemas']['ActivityScreen'];
	type Entry = components['schemas']['ActivityEntry'];

	/**
	 * The Activity History dialog (P4-D7), as the Django fill_history.html
	 * the episode row's history button opens: each entry's date and changes,
	 * Edit (the track dialog for that play) and Delete.
	 */
	let {
		target,
		onclose,
		onedit
	}: {
		target: TrackTarget;
		onclose: (changed: boolean) => void;
		onedit: (instanceId: number) => void;
	} = $props();

	let activity = $state.raw<Activity | null>(null);
	let entries = $state.raw<Entry[]>([]);
	let loadError = $state('');
	let problem = $state('');
	let busy = $state<number | null>(null);
	let changed = false;

	$effect(() => {
		const query = new URLSearchParams();
		if (target.season != null) query.set('season_number', String(target.season));
		if (target.episode != null) query.set('episode_number', String(target.episode));
		const path = [target.mediaType, target.source, target.mediaId].map(encodeURIComponent).join('/');
		let live = true;
		fetch(`/api/v1/activity/${path}/${query.size ? `?${query}` : ''}`, { credentials: 'same-origin' })
			.then(async (response) => {
				if (!response.ok) throw new Error(String(response.status));
				const body = (await response.json()) as Activity;
				if (!live) return;
				activity = body;
				entries = body.entries;
			})
			.catch(() => {
				if (live) loadError = tt.activityLoadFailed;
			});
		return () => {
			live = false;
		};
	});

	async function remove(entry: Entry) {
		if (busy !== null || !confirm(tt.activityDeleteConfirm)) return;
		busy = entry.id;
		problem = '';
		try {
			const response = await fetch(entry.delete_url, {
				method: 'DELETE',
				credentials: 'same-origin',
				headers: { 'x-csrftoken': await csrfToken() }
			});
			if (!response.ok) throw new Error(String(response.status));
			entries = entries.filter((other) => other.id !== entry.id);
			changed = true;
		} catch {
			problem = tt.trackSaveFailed;
		} finally {
			busy = null;
		}
	}
</script>

<Dialog.Root open onOpenChange={(open) => !open && onclose(changed)}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/70" />
		<Dialog.Content class="ct-track outline-none" aria-describedby={undefined}>
			<header class="ct-track__head">
				<Dialog.Title class="ct-track__title">{tt.activityHistory}</Dialog.Title>
				<Dialog.Close class="ct-track-icon" aria-label={t.close}>
					<X class="size-5" aria-hidden="true" />
				</Dialog.Close>
			</header>
			<div class="ct-track__form">
				{#if loadError}
					<p class="ct-track__problem" role="alert">{loadError}</p>
				{:else if !activity}
					<div class="ct-track__loading" aria-busy="true">{tt.loading}</div>
				{:else}
					{#if problem}<p class="ct-track__problem" role="alert">{problem}</p>{/if}
					<ul class="ct-collection__entries ct-activity">
						{#each entries as entry (entry.id)}
							<li class="ct-collection__entry">
								<div class="min-w-0">
									<p class="ct-activity__head">
										{#if entry.instance !== null}<span class="ct-metadata__badge">{tt.instance(entry.instance)}</span>{/if}
										<span class="ct-track__help">{entry.date}</span>
									</p>
									{#each entry.changes as change, c (c)}
										<p class="ct-metadata__text">{change}</p>
									{/each}
								</div>
								<div class="ct-activity__actions">
									{#if entry.instance_id !== null}
										<button
											type="button"
											class="ct-track-icon"
											title={tt.edit}
											aria-label={tt.editEntry(entry.date)}
											onclick={() => onedit(entry.instance_id!)}
										>
											<Pencil class="size-4" aria-hidden="true" />
										</button>
									{/if}
									<button
										type="button"
										class="ct-track-icon is-danger"
										title={tt.delete}
										aria-label={tt.deleteEntry(entry.date)}
										disabled={busy !== null}
										onclick={() => remove(entry)}
									>
										<Trash class="size-4" aria-hidden="true" />
									</button>
								</div>
							</li>
						{:else}
							<li class="ct-collection__entry"><p class="ct-track__help">{tt.activityEmpty}</p></li>
						{/each}
					</ul>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
