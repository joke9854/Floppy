<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/styles/cards.css';
	import '#lib/details/details.css';
	import Check from '@lucide/svelte/icons/check';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import { onMount } from 'svelte';
	import { replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import {
		detailApiPath,
		formWatchNow,
		seasonApiPath,
		type DetailCard,
		type DetailSeason,
		type DetailSections,
		type DetailShell
	} from '#lib/details/api.ts';
	import EpisodeRow from '#lib/details/EpisodeRow.svelte';
	import { detailLink } from '#lib/details/link.ts';
	import { csrfToken } from '#lib/csrf.ts';
	import { markWatched, type CheckOutcome, type Click } from '#lib/home/check.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import StatusChip from '#lib/home/StatusChip.svelte';
	import { libraryHref } from '#lib/shell/nav.ts';
	import { t } from '#lib/strings.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// The hero, refreshed after a watch is saved (the next episode moves on).
	let fresh = $state<{ for: DetailShell; shell: DetailShell } | null>(null);
	const shell = $derived(fresh?.for === data.shell ? fresh.shell : data.shell);

	// The sections stream in after first paint (undefined while they load).
	let resolved = $state<{ for: Promise<DetailSections | null>; value: DetailSections | null } | null>(
		null
	);
	$effect(() => {
		const pending = data.sections;
		pending.then((value) => {
			if (data.sections === pending) resolved = { for: pending, value };
		});
	});
	const sections = $derived(resolved?.for === data.sections ? resolved.value : undefined);

	// The season on screen: the sections' own, until a pill or "Show more"
	// loads another batch.
	let seasonState = $state<{
		for: DetailSections | null | undefined;
		season: DetailSeason | null;
		selected: number | null;
		loading: boolean;
		failed: boolean;
	} | null>(null);
	const current = $derived(
		seasonState && seasonState.for === sections
			? seasonState
			: {
					for: sections,
					season: sections?.season ?? null,
					selected: sections?.season?.number ?? null,
					loading: false,
					failed: false
				}
	);

	async function readSeason(query: string): Promise<DetailSeason | null> {
		const response = await fetch(seasonApiPath(shell.source, shell.media_id, query), {
			credentials: 'same-origin'
		});
		if (!response.ok) throw new Error(String(response.status));
		return (await response.json()) as DetailSeason;
	}

	async function pickSeason(number: number) {
		if (number === current.selected && current.season) return;
		const forSections = sections;
		seasonState = { ...current, selected: number, loading: true, failed: false };
		const url = new URL(page.url.href);
		url.searchParams.set('season', String(number));
		replaceState(url, page.state);
		try {
			const season = await readSeason(`season=${number}`);
			if (forSections !== sections || seasonState?.selected !== number) return;
			seasonState = { for: sections, season, selected: number, loading: false, failed: false };
		} catch {
			seasonState = { ...current, loading: false, failed: true };
		}
	}

	async function showMore() {
		const season = current.season;
		if (!season?.load_more || current.loading) return;
		seasonState = { ...current, loading: true, failed: false };
		try {
			const next = await readSeason(season.load_more.querystring);
			if (!next) return;
			seasonState = {
				...current,
				season: { ...season, episodes: [...season.episodes, ...next.episodes], load_more: next.load_more },
				loading: false
			};
		} catch {
			seasonState = { ...current, loading: false, failed: true };
		}
	}

	// After a watch: the hero's next episode and the season's counts.
	async function refresh() {
		const forShell = data.shell;
		try {
			const response = await fetch(detailApiPath(shell.media_type, shell.source, shell.media_id), {
				credentials: 'same-origin'
			});
			if (response.ok && forShell === data.shell) {
				fresh = { for: data.shell, shell: (await response.json()) as DetailShell };
			}
			if (current.selected !== null) {
				const season = await readSeason(`season=${current.selected}`);
				if (season) seasonState = { ...current, season, loading: false, failed: false };
			}
		} catch {
			// The rows already show the watch; the counts catch up on the next load.
		}
	}

	// The hero's episode: the show's next one, else the first unwatched aired
	// episode of the season on screen (as ctShell.js does).
	const heroEpisode = $derived.by(() => {
		if (shell.action?.kind !== 'episode') return null;
		if (shell.action.episode) return shell.action.episode;
		const episode = current.season?.episodes.find((row) => !row.watched && row.aired && row.check);
		return episode?.check ?? null;
	});

	let heroBusy = $state(false);
	let heroDone = $state<{ for: DetailShell } | null>(null);
	let heroProblem = $state<Exclude<CheckOutcome, 'saved'> | null>(null);
	let heroClick: Click | null = null;

	async function markHero() {
		const target = heroEpisode;
		if (!target || heroBusy) return;
		heroBusy = true;
		heroProblem = null;
		heroClick ??= { id: crypto.randomUUID(), at: new Date() };
		const outcome = await markWatched(target, heroClick, shell.track_time);
		heroBusy = false;
		if (outcome === 'saved') {
			heroClick = null;
			heroDone = { for: shell };
			await refresh();
		} else {
			heroProblem = outcome;
		}
	}

	// "Mark as watched" for a movie is the Django form, posted as is.
	let movieBusy = $state(false);
	// The form needs the CSRF token and the watch time, which only the
	// hydrated page fills in: a click before that would post an empty form.
	let hydrated = $state(false);
	onMount(() => (hydrated = true));
	async function markMovie(event: SubmitEvent) {
		event.preventDefault();
		if (movieBusy) return;
		movieBusy = true;
		const form = event.currentTarget as HTMLFormElement;
		(form.elements.namedItem('end_date') as HTMLInputElement).value = formWatchNow(
			new Date(),
			shell.track_time
		);
		try {
			(form.elements.namedItem('csrfmiddlewaretoken') as HTMLInputElement).value =
				await csrfToken();
		} catch {
			movieBusy = false;
			heroProblem = 'failed';
			return;
		}
		form.submit();
	}

	let synopsisOpen = $state(false);
	const longSynopsis = $derived(shell.synopsis.length > 260);
	const watchOn = $derived(shell.watch_on ?? sections?.watch_on ?? null);
	const backdrop = $derived(shell.backdrop ?? sections?.backdrop ?? null);
	const backHref = $derived(libraryHref(shell.media_type));

	function back(event: MouseEvent) {
		if (history.length > 1 && document.referrer.startsWith(location.origin)) {
			event.preventDefault();
			history.back();
		}
	}
</script>

<svelte:head>
	<title>{shell.title} · Floppy</title>
</svelte:head>

<main class="ct-detail">
	{#if backdrop}
		<div class="ct-detail-backdrop" aria-hidden="true">
			<img src={backdrop} alt="" decoding="async" fetchpriority="high" />
		</div>
	{/if}
	<div class="mx-auto max-w-[1400px] px-5 md:px-8">
		<a class="ct-detail-back ct-glass-control" href={backHref} onclick={back} aria-label={t.back}>
			<ChevronLeft class="size-5" aria-hidden="true" />
		</a>

		<div class="ct-detail-hero">
			<div class="ct-detail-poster">
				<img
					alt={shell.title}
					class="ct-fade-img"
					src={shell.poster}
					srcset={shell.poster_srcset || undefined}
					sizes={shell.poster_srcset ? '(min-width: 768px) 260px, 200px' : undefined}
					width="500"
					height="750"
					decoding="async"
					fetchpriority="high"
					use:fadeIn
				/>
			</div>
			<div class="ct-detail-identity">
				<h1 class="ct-detail-title">{shell.title}</h1>
				<p class="ct-detail-meta">
					<span>{shell.meta.type_label}</span>
					{#if shell.meta.genres.length}<span>{shell.meta.genres.join(', ')}</span>{/if}
					{#if shell.meta.year}<span>{shell.meta.year}</span>{/if}
					{#if shell.meta.runtime}<span>{shell.meta.runtime}</span>{/if}
					{#if shell.meta.certification}<span>{shell.meta.certification}</span>{/if}
					{#if shell.meta.seasons}<span>{t.seasonsCount(shell.meta.seasons)}</span>{/if}
					{#if shell.meta.percent}<span>{t.percentWatched(shell.meta.percent)}</span>{/if}
				</p>
				{#if shell.scores.length}
					<div class="ct-detail-chips">
						{#each shell.scores as score (score.key)}
							<span class="ct-score" title={score.label}>
								<span class="ct-score__badge" aria-hidden="true">{score.short}</span>
								<span class="sr-only">{score.label}</span>
								<span class="ct-score__rating">{score.rating}</span>
								{#if score.count !== null}<span class="ct-score__count">{t.votes(score.count)}</span>{/if}
							</span>
						{/each}
					</div>
				{/if}

				<div class="ct-detail-actions">
					{#if shell.action?.kind === 'mark'}
						<form method="post" action="/media_save" class="contents" onsubmit={markMovie}>
							<input type="hidden" name="csrfmiddlewaretoken" value="" />
							<input type="hidden" name="media_id" value={shell.media_id} />
							<input type="hidden" name="source" value={shell.source} />
							<input type="hidden" name="media_type" value={shell.media_type} />
							<input type="hidden" name="status" value="Completed" />
							<input type="hidden" name="save_as_new_entry" value="1" />
							<input type="hidden" name="next" value={page.url.pathname + page.url.search} />
							<input type="hidden" name="end_date" value="" />
							<button type="submit" class="ct-btn-primary" disabled={movieBusy || !hydrated}>
								<Check class="size-5" aria-hidden="true" />
								<span>{t.markAsWatched}</span>
							</button>
						</form>
					{:else if shell.action?.kind === 'watched'}
						<a href={shell.page_url} class="ct-btn-primary is-watched" data-sveltekit-reload>
							<Check class="size-5" aria-hidden="true" />
							<span>{t.watched}</span>
						</a>
					{:else if shell.action?.kind === 'completed' || (heroDone?.for === shell && !heroEpisode)}
						<span class="ct-btn-primary is-watched">
							<Check class="size-5" aria-hidden="true" />
							<span>{t.watched}</span>
						</span>
					{:else if heroEpisode}
						<button
							type="button"
							class="ct-btn-primary"
							disabled={heroBusy}
							onclick={markHero}
						>
							<Check class="size-5" aria-hidden="true" />
							<span>{t.markEpisode(heroEpisode.season_number, heroEpisode.episode_number)}</span>
						</button>
					{/if}
					<a
						href={shell.page_url}
						class="ct-btn-quiet"
						title={t.trackTitle}
						data-sveltekit-reload
					>
						<SlidersHorizontal class="size-4" aria-hidden="true" />
						<span>{t.track}</span>
					</a>
					{#if heroProblem}
						<p class="ct-detail-problem" role="alert">
							{heroProblem === 'unavailable' ? t.checkUnavailable : t.checkFailed}
						</p>
					{/if}
				</div>

				{#if shell.synopsis}
					<p class={['ct-detail-synopsis', longSynopsis && !synopsisOpen && 'is-clamped']}>
						{shell.synopsis}
					</p>
					{#if longSynopsis}
						<button type="button" class="ct-detail-more" onclick={() => (synopsisOpen = !synopsisOpen)}>
							{synopsisOpen ? t.showLess : t.readMore}
						</button>
					{/if}
				{/if}

				{#if watchOn && (watchOn.subscription.length || watchOn.rent_buy.length)}
					<div class="ct-watch-on">
						<span class="ct-watch-on__label">{t.watchOn}</span>
						{#each [...watchOn.subscription, ...watchOn.rent_buy] as chip (chip.name)}
							<span class="ct-watch-chip">
								<img src={chip.image} alt="" width="20" height="20" loading="lazy" decoding="async" />
								<span class="ct-watch-chip__name">{chip.name}</span>
								<span class="ct-watch-chip__offer">{chip.offer}</span>
							</span>
						{/each}
						{#if watchOn.link}
							<a class="ct-watch-on__via" href={watchOn.link} target="_blank" rel="noopener noreferrer"
								>{t.viaJustWatch}</a
							>
						{/if}
					</div>
				{/if}
			</div>
		</div>

		{#if sections === undefined}
			<div class="ct-detail-sections" aria-busy="true">
				<div class="ct-sections-skeleton"></div>
			</div>
		{:else if sections === null}
			<p class="rounded-ct-md bg-surface px-4 py-10 text-center text-muted" role="status">
				{t.sectionsFailed}
			</p>
		{:else}
			<div class="ct-detail-sections">
				{#each sections.sections as key (key)}
					{#if key === 'episodes' && sections.seasons.length}
						<section aria-labelledby="ct-episodes-title">
							<div class="ct-row-head">
								<h2 class="ct-row-title" id="ct-episodes-title">{t.episodes}</h2>
							</div>
							{#if sections.seasons.length > 1}
								<div class="ct-season-picker" role="tablist" aria-label={t.seasons}>
									{#each sections.seasons as cover (cover.number)}
										<button
											type="button"
											class="ct-season-cover"
											role="tab"
											aria-selected={cover.number === current.selected}
											onclick={() => pickSeason(cover.number)}
										>
											<span class="ct-season-cover__art">
												{#if cover.image}
													<img
														alt=""
														class="ct-fade-img"
														src={cover.image}
														width="185"
														height="278"
														loading="lazy"
														decoding="async"
														use:fadeIn
													/>
												{/if}
											</span>
											<span class="ct-season-cover__label">{cover.label}</span>
											<span class="ct-season-cover__short">{cover.short}</span>
										</button>
									{/each}
								</div>
							{/if}
							<div class={['ct-episode-list', current.loading && 'is-loading']} aria-busy={current.loading}>
								{#if current.season}
									{#if current.season.progress}
										{@const progress = current.season.progress}
										<div class="ct-season-progress">
											<p class="ct-season-progress__count">
												{t.episodesWatched(progress.watched, progress.total)}
												<span>{progress.percent}%</span>
											</p>
											{#if progress.dashes.length}
												<ol class="ct-season-dashes" aria-hidden="true">
													{#each progress.dashes as dash, index (index)}
														<li
															class={['ct-season-dash', dash.percent >= 100 && 'is-done']}
															title="{dash.label} · {dash.percent}%"
														>
															<span style:width="{dash.percent}%"></span>
														</li>
													{/each}
												</ol>
											{/if}
										</div>
									{/if}
									{#each current.season.episodes as episode (episode.episode_number)}
										<EpisodeRow {episode} trackTime={shell.track_time} onsaved={refresh} />
									{/each}
									{#if current.season.load_more}
										<div class="ct-ep-more">
											<button type="button" class="ct-row-link" onclick={showMore} disabled={current.loading}>
												{current.season.load_more.label}
											</button>
										</div>
									{/if}
								{:else if !current.failed}
									<div class="ct-ep-skeleton"></div>
									<div class="ct-ep-skeleton"></div>
									<div class="ct-ep-skeleton"></div>
								{/if}
								{#if current.failed}
									<p class="px-4 py-6 text-center text-muted" role="alert">{t.seasonFailed}</p>
								{/if}
							</div>
						</section>
					{:else if key === 'history' && sections.plays.length}
						<section aria-labelledby="ct-plays-title">
							<div class="ct-row-head">
								<h2 class="ct-row-title" id="ct-plays-title">{t.yourPlays}</h2>
								<a class="ct-row-link" href={sections.history_url} data-sveltekit-reload
									>{t.history} <ChevronRight class="size-4" aria-hidden="true" /></a
								>
							</div>
							<ul class="ct-plays">
								{#each sections.plays as play, index (index)}
									<li class="ct-play">
										<span class={['ct-play__icon', play.status === 'Completed' && 'is-done']} aria-hidden="true">
											{#if play.status === 'Completed'}
												<Check class="size-4" />
											{:else}
												<ChevronRight class="size-4" />
											{/if}
										</span>
										<span class="ct-play__text">
											<span class="ct-play__title">{play.label}</span>
											<span class="ct-play__sub"
												>{play.when}{play.score !== null ? ` · ${t.rated(play.score)}` : ''}</span
											>
										</span>
									</li>
								{/each}
							</ul>
						</section>
					{:else if key === 'related'}
						{#each sections.related as list (list.name)}
							<section aria-label={list.name}>
								<div class="ct-row-head"><h2 class="ct-row-title">{list.name}</h2></div>
								<div class="ct-detail-rail">
									{#each list.cards as card (card.url)}
										{@render poster(card)}
									{/each}
								</div>
							</section>
						{/each}
					{:else if key === 'cast' && sections.cast.length}
						<section aria-labelledby="ct-cast-title">
							<div class="ct-row-head">
								<h2 class="ct-row-title" id="ct-cast-title">{t.cast}</h2>
								{#if sections.cast_view_all_url}
									<a class="ct-row-link" href={sections.cast_view_all_url} target="_blank" rel="noopener noreferrer"
										>{t.seeAll} <ChevronRight class="size-4" aria-hidden="true" /></a
									>
								{/if}
							</div>
							<div class="ct-detail-rail">
								{#each sections.cast as person, index (index)}
									<article class="ct-person-card">
										<svelte:element
											this={person.url ? 'a' : 'div'}
											class="ct-person-link"
											href={person.url ?? undefined}
											data-sveltekit-reload={person.url ? '' : undefined}
										>
											<span class="ct-person-frame">
												{#if person.image}
													<img
														alt={person.name}
														class="ct-fade-img"
														src={person.image}
														width="185"
														height="278"
														loading="lazy"
														decoding="async"
														use:fadeIn
													/>
												{/if}
											</span>
											<span class="ct-person-primary">{person.name}</span>
											{#if person.role}<span class="ct-person-secondary">{person.role}</span>{/if}
										</svelte:element>
									</article>
								{/each}
							</div>
						</section>
					{:else if key === 'recommendations' && sections.recommendations.length}
						<section aria-labelledby="ct-more-title">
							<div class="ct-row-head">
								<h2 class="ct-row-title" id="ct-more-title">{t.moreLikeThis}</h2>
							</div>
							<div class="ct-detail-rail">
								{#each sections.recommendations as card (card.url)}
									{@render poster(card)}
								{/each}
							</div>
						</section>
					{:else if key === 'details' && sections.info.length}
						<section aria-labelledby="ct-info-title">
							<div class="ct-row-head">
								<h2 class="ct-row-title" id="ct-info-title">{t.information}</h2>
							</div>
							<dl class="ct-info-grid">
								{#each sections.info as row (row.label)}
									<div>
										<dt>{row.label}</dt>
										<dd>{row.value}</dd>
									</div>
								{/each}
							</dl>
						</section>
					{/if}
				{/each}
			</div>
		{/if}
	</div>
</main>

{#snippet poster(card: DetailCard)}
	<article class="ct-poster-card" data-media-type={card.media_type}>
		<a {...detailLink(card.url)} class="ct-poster-link">
			<span class="ct-poster-frame">
				<img
					alt={card.title}
					class="ct-poster-img ct-fade-img"
					src={card.poster}
					srcset={card.poster_srcset || undefined}
					sizes={card.poster_srcset ? '140px' : undefined}
					width="342"
					height="513"
					loading="lazy"
					decoding="async"
					use:fadeIn
				/>
			</span>
			<span class="ct-poster-title">{card.title}</span>
			<span class="ct-poster-sub">{card.subtitle}</span>
		</a>
		{#if card.status}
			<StatusChip status={card.status} />
		{/if}
	</article>
{/snippet}
