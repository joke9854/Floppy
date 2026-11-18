<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/home/home.css';
	import Activity from '@lucide/svelte/icons/activity';
	import Bell from '@lucide/svelte/icons/bell';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import { invalidate } from '$app/navigation';
	import AiringRow from '#lib/home/AiringRow.svelte';
	import NowPlayingPill from '#lib/home/NowPlayingPill.svelte';
	import ComingCard from '#lib/home/ComingCard.svelte';
	import PosterCard from '#lib/home/PosterCard.svelte';
	import ProgressCard from '#lib/home/ProgressCard.svelte';
	import Row from '#lib/home/Row.svelte';
	import { t } from '#lib/strings.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const home = $derived(data.home);
	let kind = $state<'all' | 'movie' | 'show'>('all');
	const inProgress = $derived(
		kind === 'all' ? home.in_progress : home.in_progress.filter((card) => card.kind === kind)
	);
	// Two columns of three on wide screens (A1); phones show the first.
	const airingColumns = $derived(
		[home.airing.slice(0, 3), home.airing.slice(3, 6)].filter((column) => column.length)
	);
	const empty = $derived(
		!home.in_progress.length && !home.airing.length && !home.recent.length && !home.coming_soon.length
	);
	const { catch_up, catch_up_shows, airing_count } = $derived(home.summary);

	// Let the check show green for a moment, then read Home again (the save
	// cleared Django's Home cache), as the Django card refreshes its row.
	function refreshSoon() {
		setTimeout(() => invalidate('floppy:home'), 700);
	}
</script>

<svelte:head>
	<title>{t.home} · Floppy</title>
</svelte:head>

<main
	class="ct-home mx-auto max-w-[1400px] px-5 pt-6 md:px-8 md:pt-8"
	data-mobile-grid={home.mobile_grid_layout}
>
	<header class="ct-page-head mb-6 sm:mb-8">
		<!-- Basis 0: on phones the head wraps for the Now Playing pill, and the
		     title must keep the avatar beside it rather than push it down. -->
		<div class="min-w-0 max-sm:flex-[1_1_0%]">
			<h1 class="ct-page-title">{t.home}</h1>
			{#if catch_up || airing_count}
				<p class="ct-page-sub">
					{#if catch_up}{t.catchUp(catch_up, catch_up_shows)}{/if}
					{#if catch_up && airing_count}·{/if}
					{#if airing_count}{t.airingCount(airing_count)}{/if}
				</p>
			{/if}
		</div>
		<NowPlayingPill initial={data.nowPlaying} onchange={() => invalidate('floppy:home')} />
		<a href="/settings/notifications" class="ct-page-bell" aria-label={t.notifications} title={t.notifications}>
			<Bell class="size-6" aria-hidden="true" />
		</a>
		<a href="/settings/account" class="ct-page-account" aria-label={t.accountSettings}>
			<span
				class="flex size-10 items-center justify-center rounded-full bg-surface-strong text-sm font-bold"
				aria-hidden="true">{data.username.slice(0, 2).toUpperCase()}</span
			>
		</a>
	</header>

	{#if home.in_progress.length}
		<section class="ct-home-section" aria-labelledby="ct-progress-title">
			<div class="ct-row-head">
				<h2 id="ct-progress-title" class="ct-row-title">{t.inProgress}</h2>
			</div>
			{#if home.in_progress_kinds.length > 1}
				<div class="ct-status-tabs" role="group" aria-label={t.filterInProgress}>
					{#each [['all', t.all], ['movie', t.movies], ['show', t.shows]] as const as [value, label] (value)}
						<button
							type="button"
							class="ct-status-tab"
							aria-pressed={kind === value}
							onclick={() => (kind = value)}>{label}</button
						>
					{/each}
				</div>
			{/if}
			<Row labelledby="ct-progress-title" progress>
				<!-- Keyed by the episode too: once a watch is saved the card names
				     the next episode, a new card with a fresh check. -->
				{#each inProgress as card (`${card.key}:${card.episode?.season_number}:${card.episode?.episode_number}`)}
					<ProgressCard {card} trackTime={home.track_time} onsaved={refreshSoon} />
				{/each}
			</Row>
		</section>
	{/if}

	{#if airingColumns.length}
		<section class="ct-home-section" aria-labelledby="ct-airing-title">
			<div class="ct-row-head">
				<h2 id="ct-airing-title" class="ct-row-title">{t.airingThisWeek}</h2>
				<a href="/calendar" class="ct-row-link">{t.calendar}<ChevronRight class="size-4" aria-hidden="true" /></a>
			</div>
			<div class="ct-airing">
				{#each airingColumns as column, index (index)}
					<ul class="ct-airing-list ct-card">
						{#each column as release (release.key)}
							<AiringRow {release} />
						{/each}
					</ul>
				{/each}
			</div>
		</section>
	{/if}

	{#if home.recent.length}
		<section class="ct-home-section" aria-labelledby="ct-recent-title">
			<div class="ct-row-head">
				<h2 id="ct-recent-title" class="ct-row-title">{t.recentlyWatched}</h2>
				<a href="/history" class="ct-row-link">{t.history}<ChevronRight class="size-4" aria-hidden="true" /></a>
			</div>
			<Row labelledby="ct-recent-title">
				{#each home.recent as card (card.key)}
					<PosterCard {card} />
				{/each}
			</Row>
		</section>
	{/if}

	{#if home.coming_soon.length}
		<section class="ct-home-section" aria-labelledby="ct-coming-title">
			<div class="ct-row-head">
				<h2 id="ct-coming-title" class="ct-row-title">{t.comingSoon}</h2>
			</div>
			<Row labelledby="ct-coming-title">
				{#each home.coming_soon as release (release.key)}
					<ComingCard {release} />
				{/each}
			</Row>
		</section>
	{/if}

	{#if empty}
		<div class="flex flex-col items-center justify-center rounded-ct-md bg-surface px-4 py-16 sm:py-32">
			<div class="mx-auto mb-4 flex size-16 items-center justify-center rounded-full bg-surface-strong">
				<Activity class="size-8 text-muted" aria-hidden="true" />
			</div>
			<h2 class="mb-2 text-xl font-semibold">{t.homeEmptyTitle}</h2>
			<p class="max-w-md text-center text-muted">{t.homeEmptyBody}</p>
		</div>
	{/if}
</main>
