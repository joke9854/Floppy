<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/styles/cards.css';
	import '#lib/details/details.css';
	import '#lib/details/pages.css';
	import Check from '@lucide/svelte/icons/check';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import { invalidateAll } from '$app/navigation';
	import { detailLink } from '#lib/details/link.ts';
	import { markWatched, type CheckOutcome, type Click } from '#lib/home/check.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { t } from '#lib/strings.ts';
	import { dt } from '#lib/details/strings.ts';
	import { page } from '$app/state';
	import { openTrack } from '#lib/track/open.svelte.ts';
	import type { PageProps } from './$types';

	/**
	 * The episode page (episode_details.html, CineTrack): the crumbs back to
	 * the show and season, the still (blurred until watched when the user
	 * hides spoilers), title, season and episode, runtime and air date, the
	 * scores, Mark as watched in one click, the overview, then the season's
	 * episodes, the guest stars and the key crew. The track window, rating,
	 * lists and notes stay on the Django page (Track) until the track dialog.
	 */
	let { data }: PageProps = $props();
	const episode = $derived(data.episode);

	let revealed = $state(false);
	let overviewShown = $state(false);
	let busy = $state(false);
	let problem = $state<Exclude<CheckOutcome, 'saved'> | null>(null);
	let pending: Click | null = null;

	async function mark() {
		if (!episode.check || busy) return;
		busy = true;
		problem = null;
		pending ??= { id: crypto.randomUUID(), at: new Date() };
		const outcome = await markWatched(episode.check, pending, episode.track_time);
		busy = false;
		if (outcome === 'saved') {
			pending = null;
			await invalidateAll();
		} else {
			problem = outcome;
		}
	}

	function trackEpisode() {
		openTrack({
			mediaType: 'episode',
			source: page.params.source ?? '',
			mediaId: page.params.id ?? '',
			season: Number(page.params.season),
			episode: Number(page.params.episode)
		});
	}

	const blurred = $derived(episode.blurred && !revealed);
	const hideOverview = $derived(episode.overview_hidden && !overviewShown);
</script>

<svelte:head>
	<title>{episode.title} · {episode.show_title} · Floppy</title>
</svelte:head>

<main class="ct-detail">
	{#if episode.backdrop}
		<div class="ct-detail-backdrop" aria-hidden="true">
			<img src={episode.backdrop} alt="" decoding="async" />
		</div>
	{/if}
	<div class="mx-auto max-w-[1400px] px-5 md:px-8">
		<nav class="ct-detail-crumbs" aria-label={dt.breadcrumb}>
			{#if episode.season_url}
				<a class="ct-detail-back ct-glass-control" {...detailLink(episode.season_url)} aria-label={dt.backToSeason}>
					<ChevronLeft class="size-5" aria-hidden="true" />
				</a>
			{/if}
			{#if episode.show_url}
				<a {...detailLink(episode.show_url)}>{episode.show_title}</a>
				<ChevronRight class="size-3.5" aria-hidden="true" />
			{/if}
			{#if episode.season_url}<a {...detailLink(episode.season_url)}>{episode.season_title}</a>{/if}
		</nav>

		<div class="ct-detail-hero ct-detail-hero--episode">
			<div class="ct-detail-poster">
				<img
					alt={episode.title}
					class={['ct-fade-img', blurred && 'is-blurred']}
					src={episode.still}
					width="1280"
					height="720"
					decoding="async"
					fetchpriority="high"
					use:fadeIn
				/>
				{#if blurred}
					<div class="ct-spoiler">
						<EyeOff class="size-6" aria-hidden="true" />
						<span>{dt.hiddenUntilWatched}</span>
						<button type="button" class="ct-spoiler__reveal" onclick={() => (revealed = true)}>{dt.reveal}</button>
					</div>
				{/if}
			</div>
			<div class="ct-detail-identity">
				<h1 class="ct-detail-title">{episode.title}</h1>
				<p class="ct-detail-meta">
					<span>{dt.seasonEpisode(episode.season_number, episode.display_number)}</span>
					{#if episode.runtime}<span>{episode.runtime}</span>{/if}
					{#if episode.aired}<span>{dt.aired(episode.aired)}</span>{/if}
				</p>
				{#if episode.scores.length}
					<div class="ct-detail-chips">
						{#each episode.scores as score (score.key)}
							<span class="ct-score" title={score.label}>
								<span class="ct-score__badge" aria-hidden="true">{score.short}</span>
								<span class="sr-only">{score.label}</span>
								<span class="ct-score__rating">{score.rating}</span>
								{#if score.count !== null}<span class="ct-score__count">{dt.votes(score.count)}</span>{/if}
							</span>
						{/each}
					</div>
				{/if}

				<div class="ct-detail-actions">
					{#if episode.watched}
						<!-- The track dialog, which logs a rewatch or edits the play. -->
						<button type="button" class="ct-btn-primary is-watched" onclick={trackEpisode}>
							<Check class="size-5" aria-hidden="true" />
							<span>{dt.watched}</span>
						</button>
					{:else if episode.check}
						<button type="button" class="ct-btn-primary" disabled={busy} onclick={mark}>
							<Check class="size-5" aria-hidden="true" />
							<span>{dt.markAsWatched}</span>
						</button>
					{/if}
					<button type="button" class="ct-btn-quiet" title={dt.trackTitle} onclick={trackEpisode}>
						<SlidersHorizontal class="size-4" aria-hidden="true" />
						<span>{t.track}</span>
					</button>
					<span class="ct-ep-nav">
						{#if episode.previous_url}
							<a {...detailLink(episode.previous_url)} class="ct-btn-quiet ct-btn-icon" aria-label={dt.previousEpisode} title={dt.previousEpisode}>
								<ChevronLeft class="size-4" aria-hidden="true" />
							</a>
						{/if}
						{#if episode.next_url}
							<a {...detailLink(episode.next_url)} class="ct-btn-quiet ct-btn-icon" aria-label={dt.nextEpisode} title={dt.nextEpisode}>
								<ChevronRight class="size-4" aria-hidden="true" />
							</a>
						{/if}
					</span>
					{#if problem}
						<p class="ct-detail-problem" role="alert">
							{problem === 'unavailable' ? t.checkUnavailable : t.checkFailed}
						</p>
					{/if}
				</div>

				{#if episode.overview}
					{#if hideOverview}
						<p class="ct-spoiler-text">
							<EyeOff class="size-4" aria-hidden="true" />
							<span>{dt.overviewHidden}</span>
							<button type="button" class="ct-row-link" onclick={() => (overviewShown = true)}>{dt.reveal}</button>
						</p>
					{:else}
						<p class="ct-detail-synopsis">{episode.overview}</p>
					{/if}
				{/if}
			</div>
		</div>

		<div class="ct-detail-sections">
			{#if episode.episodes.length}
				<section aria-labelledby="ct-season-strip-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-season-strip-title">
							{#if episode.season_url}<a {...detailLink(episode.season_url)}>{episode.season_title}</a>{:else}{episode.season_title}{/if}
						</h2>
						{#if episode.season_watched !== null}
							<span class="ct-row-detail">{dt.seasonWatched(episode.season_watched, episode.episodes.length)}</span>
						{/if}
					</div>
					<div class="ct-detail-rail">
						{#each episode.episodes as row (row.episode_number)}
							<a
								class="ct-ep-card"
								{...detailLink(row.url ?? '')}
								aria-current={row.current ? 'page' : undefined}
							>
								<span class="ct-ep-card__still">
									<img
										alt=""
										class={['ct-fade-img', row.blurred && 'is-blurred']}
										src={row.still}
										width="300"
										height="169"
										loading="lazy"
										decoding="async"
										use:fadeIn
									/>
									{#if row.watched}
										<span class="ct-ep-card__badge" aria-label={dt.watched}><Check class="size-3.5" /></span>
									{/if}
								</span>
								<span class="ct-ep-card__title">{row.display_number}&ensp;{row.title}</span>
								<span class="ct-ep-card__sub"
									>{row.current ? dt.thisEpisode : row.watched ? dt.watched : row.air_date || t.unknown}</span
								>
							</a>
						{/each}
					</div>
				</section>
			{/if}

			{#if episode.guest_stars.length}
				<section aria-labelledby="ct-guests-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-guests-title">{dt.guestStars}</h2>
					</div>
					<div class="ct-detail-rail">
						{#each episode.guest_stars as person, index (index)}
							{@const primary = person.role || person.name}
							<article class="ct-person-card">
								<svelte:element
									this={person.url ? 'a' : 'div'}
									class="ct-person-link"
									{...person.url ? detailLink(person.url) : {}}
								>
									<span class="ct-person-frame">
										{#if person.character_image || person.image}
											<img
												alt={primary}
												class="ct-fade-img"
												src={person.character_image || person.image}
												width="185"
												height="278"
												loading="lazy"
												decoding="async"
												use:fadeIn
											/>
										{/if}
									</span>
									<span class="ct-person-primary">{primary}</span>
									{#if person.role}<span class="ct-person-secondary">{person.name}</span>{/if}
								</svelte:element>
							</article>
						{/each}
					</div>
				</section>
			{/if}

			{#if episode.crew.length}
				<section aria-labelledby="ct-crew-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-crew-title">{dt.information}</h2>
					</div>
					<dl class="ct-info-grid">
						{#each episode.crew as member, index (index)}
							<div>
								<dt>{member.label}</dt>
								<dd>
									{#if member.url}<a {...detailLink(member.url)}>{member.name}</a>{:else}{member.name}{/if}
								</dd>
							</div>
						{/each}
					</dl>
				</section>
			{/if}
		</div>
	</div>
</main>
