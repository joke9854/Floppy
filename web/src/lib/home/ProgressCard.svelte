<script lang="ts">
	import { detailLink } from '#lib/details/link.ts';
	import Check from '@lucide/svelte/icons/check';
	import type { components } from '#lib/api/client.ts';
	import { t } from '#lib/strings.ts';
	import { markWatched, type CheckOutcome, type Click } from './check.ts';
	import { fadeIn } from '#lib/media/fade.ts';

	type Card = components['schemas']['HomeInProgressCard'];

	/**
	 * An In Progress card (board A1): a 16:9 backdrop (the poster, cropped,
	 * when no backdrop is cached), the progress line along its bottom edge and
	 * the glass check, then the title and "S2 E5 · 3 left".
	 */
	let {
		card,
		trackTime = true,
		onsaved
	}: { card: Card; trackTime?: boolean; onsaved?: () => void } = $props();

	let busy = $state(false);
	let done = $state(false);
	let problem = $state<Exclude<CheckOutcome, 'saved'> | null>(null);
	// One id and time per click: a retry of the same click reuses them, a new
	// click is a new play.
	let pending: Click | null = null;

	async function check() {
		if (!card.check || busy || done) return;
		busy = true;
		problem = null;
		pending ??= { id: crypto.randomUUID(), at: new Date() };
		const outcome = await markWatched(card.check, pending, trackTime);
		busy = false;
		if (outcome === 'saved') {
			pending = null;
			done = true;
			onsaved?.();
		} else {
			problem = outcome;
		}
	}

	const episodeLabel = $derived(
		card.episode ? `S${card.episode.season_number} E${card.episode.episode_number}` : ''
	);
</script>

<article
	class="ct-progress-card"
	data-kind={card.kind}
	style:--ct-progress="{card.progress_percent}%"
	aria-busy={busy}
>
	<div class="ct-progress-frame">
		<a {...detailLink(card.url)} class="ct-progress-media" tabindex="-1" aria-hidden="true">
			{#if card.backdrop}
				<img
					alt=""
					class="ct-progress-art ct-fade-img"
					src={card.backdrop}
					width="780"
					height="439"
					loading="lazy"
					decoding="async"
					use:fadeIn
				/>
			{:else}
				<img
					alt=""
					class="ct-progress-art is-poster ct-fade-img"
					src={card.poster}
					srcset={card.poster_srcset || undefined}
					sizes={card.poster_srcset ? '320px' : undefined}
					width="342"
					height="513"
					loading="lazy"
					decoding="async"
					use:fadeIn
				/>
			{/if}
		</a>
		{#if card.check && card.episode}
			<button
				type="button"
				class={['ct-check ct-glass-control', done && 'is-done', busy && 'is-busy']}
				aria-label={t.markWatched(card.title, card.episode.season_number, card.episode.episode_number)}
				aria-pressed={done}
				disabled={busy}
				onclick={check}
			>
				<Check class="size-5" strokeWidth={2.5} aria-hidden="true" />
			</button>
		{/if}
		<span class="ct-progress-line" aria-hidden="true"><span style:width="var(--ct-progress)"></span></span>
	</div>
	<a {...detailLink(card.url)} class="ct-progress-title">{card.title}</a>
	<span class="ct-progress-episode">
		{#if card.is_rewatch}<span class="ct-count-pill">{t.rewatch}</span>{/if}
		{#if card.episode}
			<span>{episodeLabel}</span>
			{#if card.episode.title}· {card.episode.title}{/if}
			{#if card.time_left}
				· {card.time_left}
			{:else if card.episodes_left}
				· {t.episodesLeft(card.episodes_left)}
			{/if}
		{:else if card.year}
			{card.year}
		{/if}
	</span>
	{#if card.remaining_label}
		<span class="ct-progress-episode">{t.timeLeft(card.remaining_label)}</span>
	{/if}
	{#if problem}
		<span class="ct-progress-episode text-error" role="status">
			{problem === 'unavailable' ? t.checkUnavailable : t.checkFailed}
		</span>
	{/if}
</article>
