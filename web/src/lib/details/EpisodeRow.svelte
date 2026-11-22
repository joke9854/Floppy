<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import History from '@lucide/svelte/icons/history';
	import Info from '@lucide/svelte/icons/info';
	import { markWatched, type CheckOutcome, type Click } from '#lib/home/check.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { openActivity } from '#lib/track/open.svelte.ts';
	import { detailLink } from './link.ts';
	import { t } from '#lib/strings.ts';
	import { dt } from '#lib/details/strings.ts';
	import type { DetailEpisode } from './api.ts';

	/**
	 * An episode row (ct/episode_row.html): the still (blurred while the user
	 * hides unwatched ones), the number and title, the air date or the watch,
	 * an ⓘ that opens the overview, and the check. An unwatched episode is
	 * marked in one click, as on the Django page; a watched one keeps the
	 * Django episode page for its plays.
	 */
	let {
		episode,
		trackTime = true,
		onsaved
	}: { episode: DetailEpisode; trackTime?: boolean; onsaved?: () => void } = $props();

	let revealed = $state(false);
	let open = $state(false);
	let busy = $state(false);
	let saved = $state(false);
	let problem = $state<Exclude<CheckOutcome, 'saved'> | null>(null);
	let pending: Click | null = null;

	const done = $derived(episode.watched || saved);

	async function check() {
		if (!episode.check || busy || done) return;
		busy = true;
		problem = null;
		pending ??= { id: crypto.randomUUID(), at: new Date() };
		const outcome = await markWatched(episode.check, pending, trackTime);
		busy = false;
		if (outcome === 'saved') {
			pending = null;
			saved = true;
			onsaved?.();
		} else {
			problem = outcome;
		}
	}
</script>

<article class={['ct-ep-row', episode.is_next && !done && 'is-next']} aria-busy={busy}>
	<div class="ct-ep-still">
		<img
			alt=""
			class={['ct-fade-img', episode.blurred && !revealed && !done && 'is-blurred']}
			src={episode.still}
			srcset={episode.still_srcset || undefined}
			sizes={episode.still_srcset ? '(min-width: 640px) 112px, 80px' : undefined}
			width="300"
			height="169"
			loading="lazy"
			decoding="async"
			use:fadeIn
		/>
		{#if episode.blurred && !revealed && !done}
			<button
				type="button"
				class="ct-ep-reveal"
				title={dt.revealThumbnail}
				aria-label={dt.revealThumbnail}
				onclick={() => (revealed = true)}
			>
				<EyeOff class="size-5" aria-hidden="true" />
			</button>
		{/if}
	</div>
	<div class="ct-ep-body">
		<div class="ct-ep-heading">
			{#if episode.display_number}<span class="ct-ep-number">{episode.display_number}</span>{/if}
			{#if episode.url}
				<a {...detailLink(episode.url)} class="ct-ep-title">{episode.title}</a>
			{:else}
				<span class="ct-ep-title">{episode.title}</span>
			{/if}
		</div>
		{#if episode.history}
			<span class="ct-ep-sub is-watched">{episode.history}</span>
		{:else if saved}
			<span class="ct-ep-sub is-watched">{dt.watched}</span>
		{:else if episode.is_next}
			<span class="ct-ep-sub"
				><span class="ct-ep-next">{dt.upNext}</span>{episode.runtime
					? ` · ${episode.runtime}`
					: ''}</span
			>
		{:else}
			<span class="ct-ep-sub"
				>{episode.air_date}{episode.runtime ? ` · ${episode.runtime}` : ''}</span
			>
		{/if}
		{#if problem}
			<span class="ct-ep-sub text-error" role="alert"
				>{problem === 'unavailable' ? t.checkUnavailable : t.checkFailed}</span
			>
		{/if}
	</div>
	{#if episode.overview}
		<button
			type="button"
			class="ct-ep-info"
			title={dt.episodeOverview}
			aria-label={dt.episodeOverview}
			aria-expanded={open}
			onclick={() => (open = !open)}
		>
			<Info class="size-5" aria-hidden="true" />
		</button>
	{/if}
	{#if episode.check && done}
		{@const c = episode.check}
		<button
			type="button"
			class="ct-ep-info"
			title="View your activity history"
			aria-label={`View your activity history for ${episode.title}`}
			onclick={() =>
				openActivity({
					mediaType: 'episode',
					source: c.source,
					mediaId: c.media_id,
					season: c.season_number,
					episode: c.episode_number
				})}
		>
			<History class="size-5" aria-hidden="true" />
		</button>
	{/if}
	{#if episode.check}
		<button
			type="button"
			class={['ct-ep-check', done && 'is-done']}
			disabled={busy || done}
			aria-label={done ? dt.watched : dt.markEpisodeWatched(episode.episode_number ?? 0, episode.title)}
			aria-pressed={done}
			onclick={check}
		>
			<Check class="size-5" aria-hidden="true" />
		</button>
	{/if}
	{#if open && episode.overview}
		<p class="ct-ep-overview">{episode.overview}</p>
	{/if}
</article>
