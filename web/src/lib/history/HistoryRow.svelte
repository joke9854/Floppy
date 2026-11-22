<script lang="ts">
	import History from '@lucide/svelte/icons/history';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Star from '@lucide/svelte/icons/star';
	import { djangoForm } from '#lib/csrf.ts';
	import { BASE } from '#lib/paths.ts';
	import { detailHref, reloadFor } from '#lib/shell/nav.ts';
	import { openTrack } from '#lib/track/open.svelte.ts';
	import { ht } from './strings.ts';
	import type { HistoryChoice, HistoryEntry } from './types.ts';

	/**
	 * One play (P4-E), as ct/history_row.html: its local time, poster, title,
	 * the episode or play line, runtime and score; Edit tracking (the web track
	 * dialog for that play), Add to custom lists, and this title's history.
	 */
	let {
		entry,
		lists,
		onnotice
	}: { entry: HistoryEntry; lists: HistoryChoice[]; onnotice: (message: string) => void } = $props();

	const href = $derived(entry.href ? detailHref(entry.href) : '');

	/** Add to custom lists: the page's bulk_list_add, as the Library card's menu posts it. */
	async function addTo(listId: string) {
		if (entry.item_id == null || !listId) return;
		try {
			const response = await djangoForm('/list/bulk-add', { item_ids: [String(entry.item_id)], custom_list_id: listId });
			const body = response.ok ? await response.json() : { success: false };
			onnotice(body.success === false ? ht.loadFailed : body.message || ht.added);
		} catch {
			onnotice(ht.loadFailed);
		}
	}
</script>

<li class="ct-history-row" data-media-type={entry.media_type}>
	<span class="ct-history-time" title={entry.time_title}>{entry.time}</span>
	<a class="ct-history-main" href={href || undefined} data-sveltekit-reload={reloadFor(href) || undefined}>
		<img
			alt=""
			class={['ct-history-poster', entry.square && 'is-square']}
			src={entry.poster}
			width="48"
			height={entry.square ? 48 : 72}
			loading="lazy"
			decoding="async"
		/>
		<span class="ct-history-text">
			<span class="ct-history-title">{entry.title}</span>
			<span class="ct-history-sub">
				{#if entry.code}<span class="ct-history-code">{entry.code}</span>{/if}
				{#if entry.subtitle}<span>{entry.subtitle}</span>{/if}
			</span>
			{#if entry.runtime || entry.score}
				<span class="ct-history-meta">
					{#if entry.runtime}<span>{entry.runtime}</span>{/if}
					{#if entry.score}
						<span class="ct-history-score"><Star class="size-3" aria-hidden="true" />{entry.score}</span>
					{/if}
				</span>
			{/if}
		</span>
	</a>
	{#if entry.history_query !== null}
		<div class="ct-history-actions">
			{#if entry.track}
				{@const target = entry.track}
				<button
					type="button"
					class="ct-history-action"
					title={ht.editTracking}
					aria-label={ht.editTracking}
					onclick={() =>
						openTrack({
							mediaType: target.media_type,
							source: target.source,
							mediaId: target.media_id,
							season: target.season_number,
							episode: target.episode_number,
							instanceId: target.instance_id
						})}
				>
					<Pencil class="size-4" aria-hidden="true" />
				</button>
			{/if}
			{#if lists.length && entry.item_id != null}
				<select
					class="ct-history-lists"
					title={ht.addToLists}
					aria-label={ht.addToLists}
					value=""
					onchange={(e) => {
						addTo(e.currentTarget.value);
						e.currentTarget.value = '';
					}}
				>
					<option value="" disabled>{ht.addToLists}</option>
					{#each lists as list (list.value)}
						<option value={list.value}>{list.label}</option>
					{/each}
				</select>
			{/if}
			<a class="ct-history-action" href="{BASE}/history?{entry.history_query}" title={ht.viewHistory} aria-label={ht.viewHistory}>
				<History class="size-4" aria-hidden="true" />
			</a>
		</div>
	{/if}
</li>
