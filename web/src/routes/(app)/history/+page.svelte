<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/history/history.css';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
	import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import X from '@lucide/svelte/icons/x';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import HistoryRow from '#lib/history/HistoryRow.svelte';
	import { ht } from '#lib/history/strings.ts';
	import { historyQuery, type HistoryDay } from '#lib/history/types.ts';
	import { BASE } from '#lib/paths.ts';
	import type { PageProps } from './$types';

	/**
	 * History (P4-E), as the Django page (history.html): the type pills, the
	 * month view's navigation (or a filtered view's pages), the days with
	 * one row per play, Load more on a long day, and the Filter History sheet.
	 */
	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	// The page's days; Load more replaces one in place until the next load.
	let days = $derived<HistoryDay[]>(screen.days);
	let loading = $state('');
	let notice = $state('');
	let dismissed = $state(false);
	let filtering = $state(false);
	let noticeTimer: ReturnType<typeof setTimeout> | undefined;

	const FILTER_KEYS = ['start-date', 'end-date', 'media_type', 'history_mode', 'genre', 'implied_genre'];
	const filterCount = $derived(FILTER_KEYS.filter((key) => page.url.searchParams.get(key)).length);
	const href = (query: string) => `${BASE}/history${query ? (query.startsWith('?') ? query : `?${query}`) : ''}`;

	function say(message: string) {
		notice = message;
		clearTimeout(noticeTimer);
		noticeTimer = setTimeout(() => (notice = ''), 4000);
	}

	async function more(day: HistoryDay) {
		if (loading) return;
		loading = day.key;
		try {
			const response = await fetch(day.more_url, { credentials: 'same-origin', headers: { accept: 'application/json' } });
			if (!response.ok) throw new Error(String(response.status));
			const next = (await response.json()) as HistoryDay;
			days = days.map((other) => (other.key === day.key ? { ...next, entries: [...day.entries, ...next.entries] } : other));
		} catch {
			say(ht.loadFailed);
		} finally {
			loading = '';
		}
	}

	function apply(changes: Record<string, string | null>) {
		filtering = false;
		goto(href(historyQuery(page.url.searchParams, changes)));
	}
</script>

<svelte:head>
	<title>{ht.title} · Floppy</title>
</svelte:head>

{#snippet pager()}
	{#if screen.pages > 1}
		<nav class="ct-history-pager" aria-label={ht.pages}>
			{#if screen.page > 1}
				<a class="ct-history-btn" href={href(historyQuery(page.url.searchParams, { page: String(screen.page - 1) }))}
					><ChevronLeft class="size-4" aria-hidden="true" />{ht.previous}</a
				>
			{/if}
			{#each Array.from({ length: screen.pages }, (_, i) => i + 1) as number (number)}
				{#if number === 1 || number === screen.pages || Math.abs(number - screen.page) <= 2}
					<a
						class="ct-history-btn"
						href={href(historyQuery(page.url.searchParams, { page: String(number) }))}
						aria-label={ht.page(number)}
						aria-current={number === screen.page ? 'page' : undefined}>{number}</a
					>
				{/if}
			{/each}
			{#if screen.page < screen.pages}
				<a class="ct-history-btn" href={href(historyQuery(page.url.searchParams, { page: String(screen.page + 1) }))}
					>{ht.next}<ChevronRight class="size-4" aria-hidden="true" /></a
				>
			{/if}
		</nav>
	{/if}
{/snippet}

<main class="ct-history-page mx-auto px-5 pt-6 md:px-8 md:pt-8">
	{#if screen.refreshing && !dismissed}
		<div class="ct-history-banner" role="status">
			<span>{ht.refreshing}</span>
			<button type="button" class="ct-history-action" aria-label={ht.dismiss} onclick={() => (dismissed = true)}>
				<X class="size-4" aria-hidden="true" />
			</button>
		</div>
	{/if}

	<div class="ct-history-head">
		<h1 class="ct-page-title">{ht.title}</h1>
		<nav class="ct-type-switch" aria-label={ht.mediaType}>
			<a
				class="ct-type-pill"
				href={href(historyQuery(page.url.searchParams, { media_type: null }))}
				aria-current={screen.media_type === '' ? 'page' : undefined}>{ht.all}</a
			>
			{#each screen.types as type (type.value)}
				<a
					class="ct-type-pill"
					href={href(historyQuery(page.url.searchParams, { media_type: type.value }))}
					aria-current={screen.media_type === type.value ? 'page' : undefined}>{type.label}</a
				>
			{/each}
		</nav>
	</div>

	{#if screen.month}
		{@const m = screen.month}
		<nav class="ct-history-months" aria-label={ht.months}>
			<div class="ct-history-months__side">
				{#if m.current}
					<a class="ct-history-btn" href={href(m.current.query)}><ChevronsLeft class="size-4" aria-hidden="true" />{m.current.label}</a>
				{/if}
				{#if m.newer}
					<a class="ct-history-btn" href={href(m.newer.query)}><ChevronLeft class="size-4" aria-hidden="true" />{m.newer.label}</a>
				{/if}
			</div>
			<h2 class="ct-history-months__name">{m.name}</h2>
			<div class="ct-history-months__side is-end">
				<a class="ct-history-btn" href={href(m.older.query)}>{m.older.label}<ChevronRight class="size-4" aria-hidden="true" /></a>
				<a class="ct-history-btn" href={href(m.year_back.query)}>{m.year_back.label}<ChevronsRight class="size-4" aria-hidden="true" /></a>
			</div>
		</nav>
	{/if}

	{@render pager()}

	{#each days as day (day.key || day.date)}
		<section class="ct-history-day" aria-labelledby="ct-day-{day.key}">
			<header class="ct-history-day-head">
				<h2 id="ct-day-{day.key}">
					<span class="ct-history-weekday">{day.weekday}</span>
					<span class="ct-history-date">{day.date}</span>
				</h2>
				<p class="ct-history-day-meta">{day.meta}</p>
			</header>
			<ol class="ct-history-list">
				{#each day.entries as entry, i (entry.key || i)}
					<HistoryRow {entry} lists={screen.lists} onnotice={say} />
				{/each}
			</ol>
			{#if day.more_url}
				<div class="ct-history-more">
					<button type="button" class="ct-history-btn" disabled={loading === day.key} onclick={() => more(day)}
						>{ht.loadMore(day.remaining)}</button
					>
				</div>
			{/if}
		</section>
	{:else}
		{#if !screen.refreshing}
			<div class="ct-history-empty">
				<p class="ct-history-empty__title">{ht.emptyTitle}</p>
				<p>{ht.emptyBody}</p>
			</div>
		{/if}
	{/each}

	{@render pager()}
</main>

<button type="button" class="ct-history-filter" onclick={() => (filtering = true)}>
	<SlidersHorizontal class="size-4" aria-hidden="true" />
	{filterCount ? ht.filterCount(filterCount) : ht.filters}
</button>
{#if filtering}
	{#await import('#lib/history/FilterSheet.svelte') then { default: FilterSheet }}
		<FilterSheet params={page.url.searchParams} types={screen.types} onapply={apply} onclose={() => (filtering = false)} />
	{/await}
{/if}
{#if notice}<p class="ct-history-notice" role="status">{notice}</p>{/if}
