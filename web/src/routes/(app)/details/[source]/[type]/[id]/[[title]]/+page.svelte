<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/styles/cards.css';
	import '#lib/details/details.css';
	import Check from '@lucide/svelte/icons/check';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import Link from '@lucide/svelte/icons/link';
	import Play from '@lucide/svelte/icons/play';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import { onMount } from 'svelte';
	import { replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import {
		detailApiPath,
		formWatchNow,
		seasonApiPath,
		type DetailTrailer,
		type DetailSeason,
		type DetailSections,
		type DetailShell
	} from '#lib/details/api.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { csrfToken } from '#lib/csrf.ts';
	import { markWatched, type CheckOutcome, type Click } from '#lib/home/check.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { libraryHref } from '#lib/shell/nav.ts';
	import { t } from '#lib/strings.ts';
	import { dt } from '#lib/details/strings.ts';
	import { openTrack } from '#lib/track/open.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	/** What the hero opened lazily: the sessions dialog or a ratings graph (P4-L3b). */
	let lazy = $state<{ query?: string; graph?: { kind: 'provider' | 'trakt' | 'imdb'; url: string } } | null>(null);

	function trackTitle() {
		openTrack({ mediaType: shell.media_type, source: shell.source, mediaId: shell.media_id });
	}

	// The hero, refreshed after a watch is saved (the next episode moves on).
	let fresh = $state.raw<{ for: DetailShell; shell: DetailShell } | null>(null);
	const shell = $derived(fresh?.for === data.shell ? fresh.shell : data.shell);

	// The sections stream in after first paint (undefined while they load).
	let resolved = $state.raw<{ for: Promise<DetailSections | null>; value: DetailSections | null } | null>(
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
	let seasonState = $state.raw<{
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
		const response = await fetch(seasonApiPath(shell.media_type === 'anime' ? 'anime' : 'tv', shell.source, shell.media_id, query), {
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
	let heroDone = $state.raw<{ for: DetailShell } | null>(null);
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
	// fanart.tv's poster and title logo, from the cache or once the sections fetched them.
	const fanartPoster = $derived(shell.fanart_poster ?? sections?.fanart_poster ?? null);
	const logo = $derived(shell.logo ?? sections?.logo ?? null);
	let logoLoaded = $state(false);

	// Trailers load on their own (the page's ?fragment=trailers), TMDB titles only.
	let trailers = $state.raw<{ for: DetailShell; list: DetailTrailer[] } | null>(null);
	const trailerList = $derived(trailers?.for === data.shell ? trailers.list : []);
	let playing = $state<string | null>(null);
	$effect(() => {
		const forShell = data.shell;
		if (forShell.source !== 'tmdb') return;
		fetch(detailApiPath(forShell.media_type, forShell.source, forShell.media_id, 'trailers'), {
			credentials: 'same-origin'
		})
			.then((response) => (response.ok ? response.json() : { trailers: [] }))
			.then((body: { trailers: DetailTrailer[] }) => {
				if (data.shell === forShell) trailers = { for: forShell, list: body.trailers };
			})
			.catch(() => {});
	});

	// The season info dialog: a season's own read, opened from its cover.
	let seasonInfo = $state<{ number: number; info: DetailSeason['info'] | null } | null>(null);
	let seasonInfoOpen = $state(false);
	async function openSeasonInfo(number: number) {
		seasonInfo = { number, info: null };
		seasonInfoOpen = true;
		try {
			const season = await readSeason(`season=${number}`);
			if (seasonInfo?.number === number) seasonInfo = { number, info: season?.info ?? null };
		} catch {
			seasonInfoOpen = false;
		}
	}
	let linksOpen = $state(false);

	// W marks the hero's episode (ct/detail_hero.html's <kbd>W</kbd>), unless
	// typing, with a modifier, or while a dialog is open.
	function shortcut(event: KeyboardEvent) {
		if (event.key.toLowerCase() !== 'w' || event.ctrlKey || event.metaKey || event.altKey) return;
		const target = event.target as HTMLElement | null;
		if (target?.closest('input, textarea, select, [contenteditable="true"]')) return;
		if (document.querySelector('[role="dialog"]')) return;
		if (shell.action?.kind !== 'episode' || !heroEpisode || heroBusy) return;
		event.preventDefault();
		markHero();
	}
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

<svelte:window onkeydown={shortcut} />

{#if playing}
	<!-- Loaded on first play: kept out of the page's first load (bundle budget). -->
	{#await import('#lib/details/TrailerPlayer.svelte') then player}
		<player.default bind:key={playing} />
	{/await}
{/if}

<Dialog bind:open={linksOpen} title={dt.links} sheet>
	{#each shell.links.filter((section) => section.links.length) as section (section.title)}
		<div class="ct-links-section">
			<div class="ct-links-title">{section.title}</div>
			<div class="ct-links">
				{#each section.links as link (link.url)}
					<a class="ct-link-chip" href={link.url} target="_blank" rel="noreferrer">
						<span class="ct-link-chip__badge">
							{#if link.logo}<img src={link.logo} alt="" />{:else}{link.fallback}{/if}
						</span>
						{link.label}
					</a>
				{/each}
			</div>
		</div>
	{/each}
</Dialog>

<Dialog
	bind:open={seasonInfoOpen}
	title={sections?.seasons.find((cover) => cover.number === seasonInfo?.number)?.label ?? dt.seasons}
	sheet
>
	{#if seasonInfo?.info}
		{@const info = seasonInfo.info}
		{#await import('#lib/details/SeasonInfo.svelte') then view}
			<view.default {info} />
		{/await}
	{:else}
		<div class="ct-sections-skeleton"></div>
	{/if}
</Dialog>

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
				{#if fanartPoster}
					<img
						alt={shell.title}
						class="ct-fade-img"
						src={fanartPoster}
						width="1000"
						height="1426"
						decoding="async"
						fetchpriority="high"
						use:fadeIn
					/>
				{:else}
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
				{/if}
			</div>
			<div class="ct-detail-identity">
				<h1 class="ct-detail-title">
					{#if logo}
						<!-- The text holds the place until fanart.tv's logo has loaded. -->
						<span class:sr-only={logoLoaded}>{shell.title}</span>
						<img
							alt=""
							aria-hidden="true"
							class="ct-detail-title__logo"
							class:hidden={!logoLoaded}
							src={logo}
							decoding="async"
							onload={() => (logoLoaded = true)}
						/>
					{:else}
						{shell.title}
					{/if}
				</h1>
				<p class="ct-detail-meta">
					<span>{shell.meta.type_label}</span>
					{#if shell.meta.genres.length}<span>{shell.meta.genres.join(', ')}</span>{/if}
					{#if shell.meta.year}<span>{shell.meta.year}</span>{/if}
					{#if shell.meta.runtime}<span>{shell.meta.runtime}</span>{/if}
					{#if shell.meta.certification}<span>{shell.meta.certification}</span>{/if}
					{#if shell.meta.seasons}<span>{dt.seasonsCount(shell.meta.seasons)}</span>{/if}
					{#snippet line(text: string)}
						{#if shell.meta.sessions_query}
							<span>
								<button
									type="button"
									class="ct-meta-link"
									onclick={() => (lazy = { query: shell.meta.sessions_query! })}>{text}</button
								>
							</span>
						{:else}
							<span>{text}</span>
						{/if}
					{/snippet}
					{#if shell.meta.percent}{@render line(dt.percentWatched(shell.meta.percent))}{/if}
					{#if shell.meta.series}<span>{shell.meta.series}</span>{/if}
					{#if shell.meta.progress}{@render line(shell.meta.progress)}{/if}
				</p>
				{#if shell.scores.length}
					<div class="ct-detail-chips">
						{#each shell.scores as score (score.key)}
							{@const kind = shell.graphs.find((graph) => graph === score.key) as
								| 'provider'
								| 'trakt'
								| 'imdb'
								| undefined}
							{#snippet chip()}
								<span class="ct-score__badge" aria-hidden="true">{score.short}</span>
								<span class="sr-only">{score.label}</span>
								<span class="ct-score__rating">{score.rating}</span>
								{#if score.count !== null}<span class="ct-score__count">{dt.votes(score.count)}</span>{/if}
							{/snippet}
							{#if kind}
								<button
									type="button"
									class="ct-score"
									title="{score.label} ratings graph"
									onclick={() =>
										(lazy = {
											graph: {
												kind,
												url: `/api/v1/details/${shell.media_type}/${shell.source}/${encodeURIComponent(shell.media_id)}/graphs/`
											}
										})}>{@render chip()}</button
								>
							{:else}
								<span class="ct-score" title={score.label}>{@render chip()}</span>
							{/if}
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
								<span>{dt.markAsWatched}</span>
							</button>
						</form>
					{:else if shell.action?.kind === 'watched'}
						<!-- The track dialog, which logs another play or edits this one. -->
						<button type="button" class="ct-btn-primary is-watched" onclick={trackTitle}>
							<Check class="size-5" aria-hidden="true" />
							<span>{dt.watched}</span>
						</button>
					{:else if shell.action?.kind === 'completed' || (heroDone?.for === shell && !heroEpisode)}
						<span class="ct-btn-primary is-watched">
							<Check class="size-5" aria-hidden="true" />
							<span>{dt.watched}</span>
						</span>
					{:else if heroEpisode}
						<button
							type="button"
							class="ct-btn-primary"
							disabled={heroBusy}
							onclick={markHero}
						>
							<Check class="size-5" aria-hidden="true" />
							<span>{dt.markEpisode(heroEpisode.season_number, heroEpisode.episode_number)}</span>
						</button>
					{/if}
					<button type="button" class="ct-btn-quiet" title={dt.trackTitle} onclick={trackTitle}>
						<SlidersHorizontal class="size-4" aria-hidden="true" />
						<span>{t.track}</span>
					</button>
					{#if trailerList.length}
						<button type="button" class="ct-btn-quiet" onclick={() => (playing = trailerList[0].key)}>
							<Play class="size-4" aria-hidden="true" />
							<span>{dt.trailer}</span>
						</button>
					{/if}
					{#if shell.links.some((section) => section.links.length)}
						<button
							type="button"
							class="ct-btn-quiet ct-btn-icon"
							aria-label={dt.links}
							title={dt.links}
							onclick={() => (linksOpen = true)}
						>
							<Link class="size-4" aria-hidden="true" />
						</button>
					{/if}
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
							{synopsisOpen ? dt.showLess : dt.readMore}
						</button>
					{/if}
				{/if}

				{#if watchOn && (watchOn.subscription.length || watchOn.rent_buy.length)}
					<div class="ct-watch-on">
						<span class="ct-watch-on__label">{dt.watchOn}</span>
						{#each [...watchOn.subscription, ...watchOn.rent_buy] as chip (chip.name)}
							<span class="ct-watch-chip">
								<img src={chip.image} alt="" width="20" height="20" loading="lazy" decoding="async" />
								<span class="ct-watch-chip__name">{chip.name}</span>
								<span class="ct-watch-chip__offer">{chip.offer}</span>
							</span>
						{/each}
						{#if watchOn.link}
							<a class="ct-watch-on__via" href={watchOn.link} target="_blank" rel="noopener noreferrer"
								>{dt.viaJustWatch}</a
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
				{dt.sectionsFailed}
			</p>
		{:else}
			<!-- Loaded with the sections: the page's first load is the hero alone (bundle budget). -->
			{#await import('#lib/details/Sections.svelte')}
				<div class="ct-detail-sections" aria-busy="true">
					<div class="ct-sections-skeleton"></div>
				</div>
			{:then view}
				<view.default
					{sections}
					mediaType={shell.media_type}
					source={shell.source}
					mediaId={shell.media_id}
					{current}
					trailers={trailerList}
					trackTime={shell.track_time}
					onpick={pickSeason}
					onmore={showMore}
					onsaved={refresh}
					oninfo={openSeasonInfo}
					onplay={(key: string) => (playing = key)}
				/>
			{/await}
		{/if}
	</div>
</main>

{#if lazy}
	{#await import('#lib/details/HeroLazy.svelte') then { default: HeroLazy }}
		<HeroLazy {...lazy} onclose={() => (lazy = null)} />
	{/await}
{/if}
