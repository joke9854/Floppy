<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/statistics/statistics.css';
	import CalendarRange from '@lucide/svelte/icons/calendar-range';
	import Layers from '@lucide/svelte/icons/layers';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import SlidersVertical from '@lucide/svelte/icons/sliders-vertical';
	import { untrack } from 'svelte';
	import { goto, invalidate, replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { djangoForm } from '#lib/csrf.ts';
	import { BASE } from '#lib/paths.ts';
	import Heatmap from '#lib/statistics/Heatmap.svelte';
	import Highlights from '#lib/statistics/Highlights.svelte';
	import SummaryCards from '#lib/statistics/SummaryCards.svelte';
	import { st } from '#lib/statistics/strings.ts';
	import { hoursBars, rebuilding, TYPE_FLAVOUR, TYPE_NOUN, withQuery } from '#lib/statistics/types.ts';
	import type { PageProps } from './$types';

	/**
	 * Statistics (P4-H1), as the Django page (app/statistics.html): the range,
	 * media-type and compare controls, Refresh and the Monthly recap, the hero,
	 * the highlight cards, the summary cards, Activity History or Played Hours
	 * by Media Type, and the Statistics Preferences. The media type switches
	 * in the browser (kept in `media-type`), as on the page; a range or compare
	 * change reloads. While the range's statistics rebuild it waits on their
	 * cache status and reloads.
	 */
	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	// Seeded from `media-type` on each load; the menu sets it in place.
	let mediaType = $derived.by(() => {
		const wanted = page.url.searchParams.get('media-type') ?? 'all';
		return screen.media_types.some((option) => option.value === wanted) ? wanted : 'all';
	});
	const typeLabel = $derived(screen.media_types.find((option) => option.value === mediaType)?.label ?? '');
	const summary = $derived(screen.summaries[mediaType] ?? null);
	const highlights = $derived(screen.highlights[mediaType] ?? null);
	const rangeLabel = $derived(st.rangeNames[screen.range.name] ?? screen.range.label);
	const compareLabel = $derived(
		screen.compare.options.find((option) => option.value === screen.compare.mode)?.label ?? ''
	);
	const bars = $derived.by(() => {
		const all = hoursBars(screen.played_hours, screen.range.first_day, screen.range.last_day);
		if (mediaType === 'all') return all;
		return { ...all, series: all.series.filter((series) => series.media_type === mediaType) };
	});
	const hasHours = $derived(bars.series.some((series) => series.values.some((value) => value > 0)));

	let rangeMenu = $state<HTMLDetailsElement>();
	let typeMenu = $state<HTMLDetailsElement>();
	let compareMenu = $state<HTMLDetailsElement>();
	let customTab = $state(false);
	let customStart = $state('');
	let customEnd = $state('');
	let refreshing = $state(false);
	let refreshedNote = $state(false);
	let preferencesOpen = $state(false);
	// Loaded on first use: the sheet when it opens, the bars in the Stacked view.
	let preferencesLoaded = $state(false);
	const loadPreferences = () => import('#lib/statistics/PreferencesDialog.svelte');
	const loadBars = () => import('#lib/statistics/StackedBars.svelte');
	// H2's charts sit below the cards: loaded after the page, as their own chunks.
	const chartsTop = import.meta.env.SSR ? null : import('#lib/statistics/ChartsTop.svelte');
	const chartsRest = import.meta.env.SSR ? null : import('#lib/statistics/ChartsRest.svelte');
	// H3: the talent section (all, TV, movies, anime, games) and the overviews.
	const talentSection = import.meta.env.SSR ? null : import('#lib/statistics/Talent.svelte');
	const overviewSection = import.meta.env.SSR ? null : import('#lib/statistics/Overviews.svelte');
	const TALENT_TYPES = new Set(['all', 'tv', 'movie', 'anime', 'game']);
	let failed = $state('');
	let watchGeneration = 0;

	function closeMenus(except?: HTMLDetailsElement) {
		for (const menu of [rangeMenu, typeMenu, compareMenu]) if (menu && menu !== except) menu.open = false;
	}

	function pickType(value: string) {
		closeMenus();
		// A shallow replace does not update page.url: set the type here too.
		mediaType = value;
		// The page switches the type in place and keeps it in the URL.
		const url = new URL(page.url.href);
		if (value === 'all') url.searchParams.delete('media-type');
		else url.searchParams.set('media-type', value);
		replaceState(url, page.state);
	}

	function goRange(start: string, end: string) {
		closeMenus();
		goto(`${BASE}/statistics${withQuery(page.url.searchParams, { 'start-date': start, 'end-date': end })}`, {
			reset: false
		});
	}

	async function pickCompare(value: string) {
		closeMenus();
		try {
			const response = await djangoForm(screen.urls.compare, { compare_mode: value });
			if (!response.ok) throw new Error(String(response.status));
		} catch {
			failed = st.failed;
			return;
		}
		goto(`${BASE}/statistics${withQuery(page.url.searchParams, { compare: value })}`, { reset: false });
	}

	/** Waits on the range's statistics cache (the page's CacheUpdater), then reloads. */
	async function waitForRebuild(manual: boolean) {
		if (!screen.range.predefined) {
			await invalidate('floppy:statistics');
			return;
		}
		refreshing = true;
		const generation = watchGeneration;
		const params = new URLSearchParams({ cache_type: 'statistics', range_name: screen.range.name });
		for (let attempt = 0; attempt < 60; attempt++) {
			await new Promise((resolve) => setTimeout(resolve, 3000));
			if (generation !== watchGeneration) return;
			try {
				const response = await fetch(`${screen.urls.status}?${params}`, { credentials: 'same-origin' });
				if (!response.ok) break;
				const status = await response.json();
				const done = !rebuilding(status) && status.exists && (!manual || (status.recently_built && !status.is_stale));
				if (done) {
					await invalidate('floppy:statistics');
					if (manual) {
						refreshedNote = true;
						setTimeout(() => (refreshedNote = false), 5000);
					}
					break;
				}
			} catch {
				break;
			}
		}
		if (generation === watchGeneration) refreshing = false;
	}

	async function refresh() {
		if (refreshing) return;
		if (!screen.range.predefined) {
			await invalidate('floppy:statistics');
			return;
		}
		try {
			const response = await djangoForm(screen.urls.refresh, { range_name: screen.range.name });
			if (!response.ok) throw new Error(String(response.status));
		} catch {
			failed = st.failed;
			return;
		}
		waitForRebuild(true);
	}

	// A wait for this range ends when the page shows another range.
	const view = $derived(`${screen.range.start}:${screen.range.end}:${screen.compare.mode}`);
	$effect(() => {
		void view;
		return () => {
			watchGeneration++;
			refreshing = false;
		};
	});

	$effect(() => {
		// The page checks the cache on load: a rebuild in progress shows the
		// banner and reloads when it ends.
		if (!screen.range.predefined || untrack(() => refreshing)) return;
		const params = new URLSearchParams({ cache_type: 'statistics', range_name: screen.range.name });
		fetch(`${screen.urls.status}?${params}`, { credentials: 'same-origin' })
			.then((response) => (response.ok ? response.json() : null))
			.then((status) => {
				if (status && rebuilding(status)) waitForRebuild(false);
			})
			.catch(() => {});
	});

	$effect(() => {
		// The custom range starts from the range shown.
		customStart = screen.range.first_day;
		customEnd = screen.range.last_day;
	});

	const format = (value: number) => value.toLocaleString('en-US');
</script>

<svelte:head><title>Statistics - Floppy</title></svelte:head>

<main class="ct-stats mx-auto max-w-[1400px] px-5 pt-6 md:px-8 md:pt-8">
	<header class="ct-page-head">
		<h1 class="ct-page-title">{st.title}</h1>
	</header>

	{#if refreshing}<p class="ct-stats-banner">{st.refreshing}</p>{/if}
	{#if refreshedNote}<p class="ct-stats-banner is-done" role="status">{st.refreshed}</p>{/if}
	{#if failed}<p class="ct-stats-banner is-error" role="alert">{failed}</p>{/if}

	<div class="ct-stats-tools">
		<details class="ct-stats-menu" bind:this={rangeMenu} ontoggle={() => rangeMenu?.open && closeMenus(rangeMenu)}>
			<summary class="ct-stats-button">
				<CalendarRange class="size-5 ct-stats-accent" aria-hidden="true" />
				<span>{rangeLabel}</span>
				<i class="ct-stats-caret" aria-hidden="true"></i>
			</summary>
			<div class="ct-stats-menu__panel is-wide">
				<div class="ct-stats-tabs" role="tablist">
					<button type="button" role="tab" aria-selected={!customTab} onclick={() => (customTab = false)}>{st.predefined}</button>
					<button type="button" role="tab" aria-selected={customTab} onclick={() => (customTab = true)}>{st.custom}</button>
				</div>
				{#if !customTab}
					{#each screen.ranges as preset (preset.name)}
						<button
							type="button"
							class="ct-stats-menu__item"
							aria-current={screen.range.name === preset.name ? 'true' : undefined}
							onclick={() => goRange(preset.start, preset.end)}
						>
							<span>{st.rangeNames[preset.name] ?? preset.name}</span>
							<small>{preset.dates}</small>
						</button>
					{/each}
				{:else}
					<form
						class="ct-stats-custom"
						onsubmit={(event) => {
							event.preventDefault();
							if (customStart && customEnd) goRange(customStart, customEnd);
						}}
					>
						<label><span>{st.startDate}</span><input type="date" bind:value={customStart} required /></label>
						<label><span>{st.endDate}</span><input type="date" bind:value={customEnd} min={customStart} required /></label>
						<div class="ct-stats-custom__actions">
							<button type="button" class="ct-stats-button" onclick={() => closeMenus()}>{st.cancel}</button>
							<button type="submit" class="ct-stats-button is-primary">{st.applyRange}</button>
						</div>
					</form>
				{/if}
			</div>
		</details>

		<details class="ct-stats-menu" bind:this={typeMenu} ontoggle={() => typeMenu?.open && closeMenus(typeMenu)}>
			<summary class="ct-stats-button">
				<Layers class="size-5 ct-stats-accent" aria-hidden="true" />
				<span>{typeLabel}</span>
				<i class="ct-stats-caret" aria-hidden="true"></i>
			</summary>
			<div class="ct-stats-menu__panel">
				{#each screen.media_types as option (option.value)}
					<button
						type="button"
						class="ct-stats-menu__item"
						aria-current={mediaType === option.value ? 'true' : undefined}
						onclick={() => pickType(option.value)}
					>
						<span>{option.label}</span>
					</button>
				{/each}
			</div>
		</details>

		{#if screen.range.finite}
			<details class="ct-stats-menu" bind:this={compareMenu} ontoggle={() => compareMenu?.open && closeMenus(compareMenu)}>
				<summary class="ct-stats-button">
					<span class="ct-stats-muted">{st.compareTo}</span>
					<span>{compareLabel}</span>
					<i class="ct-stats-caret" aria-hidden="true"></i>
				</summary>
				<div class="ct-stats-menu__panel">
					{#each screen.compare.options as option (option.value)}
						<button
							type="button"
							class="ct-stats-menu__item"
							aria-current={screen.compare.mode === option.value ? 'true' : undefined}
							onclick={() => pickCompare(option.value)}
						>
							<span>{option.label}</span>
							{#if option.dates}<small>{option.dates}</small>{/if}
						</button>
					{/each}
				</div>
			</details>
		{/if}

		<button
			type="button"
			class="ct-stats-button is-icon"
			aria-label={st.refresh}
			title={st.refresh}
			disabled={refreshing}
			onclick={refresh}
		>
			<RefreshCw class={['size-5', refreshing && 'ct-stats-spin']} aria-hidden="true" />
		</button>
		<a class="ct-stats-button" href={screen.urls.recap} data-sveltekit-reload>{st.recap}</a>
	</div>

	{#if screen.database_error}
		<p class="ct-stats-banner is-error" role="alert">{st.databaseError}</p>
	{:else}
		<section class="ct-stats-hero">
			<div class="ct-stats-hero__copy">
				<p class="ct-stats-hero__lead">
					{st.heroSpent(format(summary?.total_hours ?? 0))}
					<br />
					{st.heroWith(format(summary?.total ?? 0), TYPE_NOUN[mediaType] ?? 'titles')}
				</p>
				<p class="ct-stats-hero__sub">
					{st.heroDays(format(summary?.total_days ?? 0), TYPE_FLAVOUR[mediaType] ?? TYPE_FLAVOUR.all)}
				</p>
			</div>
			{#if highlights}<Highlights {highlights} />{/if}
		</section>

		<SummaryCards {summary} activity={screen.activity} scaleMax={screen.rating_scale_max} />

		{#if chartsTop}
			{#await chartsTop then { default: ChartsTop }}<ChartsTop {screen} {mediaType} />{/await}
		{/if}

		{#if screen.preferences.activity_history_view !== 'stacked' && screen.heatmap}
			<Heatmap heatmap={screen.heatmap} />
		{/if}

		{#if chartsRest}
			{#await chartsRest then { default: ChartsRest }}<ChartsRest {screen} {mediaType} />{/await}
		{/if}

		{#if screen.preferences.activity_history_view !== 'heatmap'}
			<section class="ct-stats-card">
				<h2 class="ct-stats-card__title is-center">{st.playedHours}</h2>
				{#if hasHours}
					{#await loadBars() then { default: StackedBars }}
						<StackedBars {bars} unit={st.hours.toLowerCase()} label={st.playedHours} />
					{/await}
				{:else}
					<div class="ct-stats-empty">
						<h3>{st.noContent}</h3>
						<p>{st.noContentBody}</p>
					</div>
				{/if}
			</section>
		{/if}

		{#if talentSection && TALENT_TYPES.has(mediaType)}
			{#await talentSection then { default: Talent }}<Talent {screen} {mediaType} />{/await}
		{/if}

		{#if overviewSection}
			{#await overviewSection then { default: Overviews }}<Overviews {screen} {mediaType} />{/await}
		{/if}
	{/if}
</main>

<button
	type="button"
	class="ct-stats-prefs-button"
	aria-label={st.preferences}
	title={st.preferences}
	onclick={() => {
		preferencesLoaded = true;
		preferencesOpen = true;
	}}
>
	<SlidersVertical class="size-5" aria-hidden="true" />
</button>

{#if preferencesLoaded}
	{#await loadPreferences() then { default: PreferencesDialog }}
		<PreferencesDialog
			bind:open={preferencesOpen}
			preferences={screen.preferences}
			url={screen.urls.preferences}
			onsaved={async () => {
				// A view change shows at once; new formats and scales rebuild first.
				await invalidate('floppy:statistics');
				waitForRebuild(false);
			}}
		/>
	{/await}
{/if}
