<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/library/library.css';
	import ArrowDownWideNarrow from '@lucide/svelte/icons/arrow-down-wide-narrow';
	import ArrowUpNarrowWide from '@lucide/svelte/icons/arrow-up-narrow-wide';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import LayoutGrid from '@lucide/svelte/icons/layout-grid';
	import Settings2 from '@lucide/svelte/icons/settings-2';
	import TableIcon from '@lucide/svelte/icons/table-2';
	import SearchIcon from '@lucide/svelte/icons/search';
	import { DropdownMenu } from 'bits-ui';
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import type { Component } from 'svelte';
	import { lazyComponent } from '#lib/library/lazy.ts';
	import type { ViewMenuProps } from '#lib/library/view-menu.ts';
	import ChoiceMenu from '#lib/library/ChoiceMenu.svelte';
	import FilterMenu from '#lib/library/LazyFilterMenu.svelte';
	import type { ParamChanges } from '#lib/library/filters.ts';
	import LibraryCard from '#lib/library/LibraryCard.svelte';
	import {
		libraryApiPath,
		withParams,
		type LibraryCard as Card,
		type LibraryScreen
	} from '#lib/library/query.ts';
	import { BASE } from '#lib/paths.ts';
	import { libraryHref } from '#lib/shell/nav.ts';
	import { t } from '#lib/strings.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const screen = $derived(data.screen);

	// Later pages, read as the list scrolls. A new list (another type, sort,
	// status or search) starts again from the page the load returned.
	let more = $state.raw<{ for: LibraryScreen | null; cards: Card[]; page: number; hasNext: boolean }>({
		for: null,
		cards: [],
		page: 1,
		hasNext: false
	});
	const current = $derived(
		more.for === screen ? more : { for: screen, cards: [], page: screen.page, hasNext: screen.has_next }
	);
	const cards = $derived([...screen.results, ...current.cards]);
	let loading = $state(false);
	let loadFailed = $state(false);

	async function loadMore() {
		if (loading || !current.hasNext) return;
		loading = true;
		loadFailed = false;
		const forScreen = screen;
		try {
			const response = await fetch(
				libraryApiPath(screen.media_type, page.url.searchParams, current.page + 1),
				{ credentials: 'same-origin' }
			);
			if (!response.ok) throw new Error(String(response.status));
			const next = (await response.json()) as LibraryScreen;
			if (forScreen !== screen) return; // the list changed meanwhile
			more = {
				for: screen,
				cards: [...current.cards, ...next.results],
				page: next.page,
				hasNext: next.has_next
			};
		} catch {
			loadFailed = true;
		} finally {
			loading = false;
		}
	}

	function revealed(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((entry) => entry.isIntersecting)) loadMore();
			},
			{ rootMargin: '600px 0px' }
		);
		observer.observe(node);
		return { destroy: () => observer.disconnect() };
	}

	// Sort and status are buttons, not links: the load saves them as the
	// user's preferences, which a hover preload must never do.
	function change(changes: ParamChanges, replace = false) {
		goto(withParams(page.url.href, changes), { reset: false, replace });
	}

	const statusValue = $derived(screen.statuses.length === 1 ? screen.statuses[0] : 'all');
	const statusOptions = $derived([{ value: 'all', label: t.all }, ...screen.status_choices]);
	const statusLabel = $derived(
		statusOptions.find((option) => option.value === statusValue)?.label ?? t.all
	);
	const sortLabel = $derived(screen.sorts.find((sort) => sort.value === screen.sort)?.label ?? '');

	// Select mode (B4) and the selection, for this type and view only.
	const listKey = $derived(`${screen.media_type}:${screen.subview}`);
	let selectingFor = $state('');
	let selection = $state.raw<{ for: string; ids: number[] }>({ for: '', ids: [] });
	const selecting = $derived(selectingFor === listKey && screen.bulk !== null);
	const selected = $derived(selection.for === listKey ? selection.ids : []);
	let notice = $state('');

	function toggleSelected(key: number) {
		selection = {
			for: listKey,
			ids: selected.includes(key) ? selected.filter((id) => id !== key) : [...selected, key]
		};
	}

	function endSelect() {
		selectingFor = '';
		selection = { for: '', ids: [] };
	}

	async function bulkDone(message: string) {
		endSelect();
		notice = message;
		await invalidateAll();
	}

	// The View settings menu loads on first use (bundle budget).
	let ViewMenu = $state<Component<ViewMenuProps> | null>(null);
	let viewMenuOpen = $state(false);
	function loadViewMenu(open = false) {
		if (open) viewMenuOpen = true;
		lazyComponent<ViewMenuProps>('view-menu', () => import('#lib/library/ViewMenu.svelte')).then(
			(menu) => {
				ViewMenu = menu;
			}
		);
	}

	let search = $state('');
	let searchFor: LibraryScreen | null = null;
	$effect.pre(() => {
		// Follow the URL when the list changes from elsewhere (back, a link).
		if (searchFor !== screen && document.activeElement?.id !== 'library-search') {
			search = screen.search;
		}
		searchFor = screen;
	});
	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	function typed() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => change({ search: search.trim() || null }, true), 300);
	}
</script>

<svelte:head>
	<title>{screen.title} · Floppy</title>
</svelte:head>

<main class="mx-auto max-w-[1400px] px-5 pt-6 pb-10 md:px-8 md:pt-8">
	<div class="ct-page-head ct-library-titlebar">
		<div class="min-w-0">
			<h1 class="ct-page-title">
				<span class="ct-library-title--phone">{t.library}</span>
				<span class="ct-library-title--wide">{screen.title}</span>
			</h1>
			<p class="ct-page-sub">{t.libraryCount(screen.count, screen.title, screen.in_progress)}</p>
		</div>
		{#if screen.views.length}
			<nav class="ct-segment" aria-label={t.libraryViews}>
				{#each screen.views as view (view.media_type)}
					<a
						href="{BASE}/library/{view.media_type}"
						aria-current={view.media_type === screen.media_type ? 'page' : undefined}
						>{view.label}</a
					>
				{/each}
			</nav>
		{/if}
		{#if screen.subviews.length}
			<div class="ct-segment" role="group" aria-label={t.libraryViews}>
				{#each screen.subviews as view (view.value)}
					<button
						type="button"
						aria-pressed={view.value === screen.subview}
						onclick={() => change({ subview: view.value })}>{view.label}</button
					>
				{/each}
			</div>
		{/if}
	</div>

	<nav class="ct-type-switch" aria-label={t.library}>
		{#each data.library as type (type.media_type)}
			{@const href = libraryHref(type.media_type)}
			<a
				{href}
				class="ct-type-pill"
				data-sveltekit-reload={href.startsWith(`${BASE}/`) ? 'off' : ''}
				aria-current={type.media_type === screen.media_type ||
				(screen.media_type === 'season' && type.media_type === 'tv')
					? 'page'
					: undefined}>{type.label}</a
			>
		{/each}
	</nav>

	<div class="ct-library-bar">
		<div class="ct-status-tabs" role="group" aria-label={t.status}>
			{#each statusOptions as option (option.value)}
				<button
					type="button"
					class="ct-status-tab"
					aria-pressed={option.value === statusValue}
					onclick={() => change({ status: option.value })}>{option.label}</button
				>
			{/each}
		</div>
		<div class="ct-toolbar">
			<div class="ct-status-menu">
				<ChoiceMenu
					label={t.status}
					options={statusOptions}
					value={statusValue}
					onselect={(value) => change({ status: value })}
				>
					{#snippet trigger()}
						<span class="ct-toolbar-label">{statusLabel}</span>
						<ChevronDown class="size-4" aria-hidden="true" />
					{/snippet}
				</ChoiceMenu>
			</div>
			<label class="ct-search">
				<span class="sr-only">{t.searchLibrary}</span>
				<SearchIcon class="size-4" aria-hidden="true" />
				<input
					id="library-search"
					type="search"
					placeholder={t.searchLibrary}
					autocomplete="off"
					bind:value={search}
					oninput={typed}
				/>
			</label>
			<FilterMenu
				filters={screen.filters}
				options={screen.filter_options}
				onapply={(changes) => change(changes)}
			/>
			<ChoiceMenu
				label={t.sort}
				options={screen.sorts}
				value={screen.sort}
				onselect={(value) => change({ sort: value, direction: null })}
			>
				{#snippet trigger()}
					{#if screen.direction === 'asc'}
						<ArrowUpNarrowWide class="size-4" aria-hidden="true" />
					{:else}
						<ArrowDownWideNarrow class="size-4" aria-hidden="true" />
					{/if}
					<span class="ct-toolbar-label">{sortLabel}</span>
				{/snippet}
				{#snippet footer()}
					<DropdownMenu.Item
						class="flex h-10 cursor-pointer items-center gap-3 rounded-ct-xs px-3 text-[14px] font-semibold text-text-secondary outline-none data-highlighted:bg-white/8 data-highlighted:text-text"
						onSelect={() =>
							change({ sort: screen.sort, direction: screen.direction === 'asc' ? 'desc' : 'asc' })}
					>
						{#if screen.direction === 'asc'}
							<ArrowDownWideNarrow class="size-4 text-muted" aria-hidden="true" />
							{t.descending}
						{:else}
							<ArrowUpNarrowWide class="size-4 text-muted" aria-hidden="true" />
							{t.ascending}
						{/if}
					</DropdownMenu.Item>
				{/snippet}
			</ChoiceMenu>
			{#if screen.layout === 'table'}
				<!-- Loads with the table layout only (bundle budget). -->
				{#await import('#lib/library/LazyColumnMenu.svelte') then { default: ColumnMenu }}
					<ColumnMenu
						mediaType={screen.media_type}
						sort={screen.sort}
						config={screen.column_config}
						defaults={screen.column_defaults}
					/>
				{/await}
			{/if}
			<div class="ct-layout-switch" role="group" aria-label={t.layout}>
				<button
					type="button"
					aria-label={t.grid}
					title={t.grid}
					aria-pressed={screen.layout === 'grid'}
					onclick={() => change({ layout: 'grid' }, true)}
				>
					<LayoutGrid class="size-4" aria-hidden="true" />
				</button>
				<button
					type="button"
					aria-label={t.table}
					title={t.table}
					aria-pressed={screen.layout === 'table'}
					onclick={() => change({ layout: 'table' }, true)}
				>
					<TableIcon class="size-4" aria-hidden="true" />
				</button>
			</div>
			{#if ViewMenu}
				<ViewMenu
					mediaType={screen.media_type}
					search={page.url.searchParams}
					grouping={screen.entry_grouping}
					canSelect={screen.bulk !== null}
					{selecting}
					onselect={() => (selecting ? endSelect() : (selectingFor = listKey))}
					onnotice={(message) => (notice = message)}
					initialOpen={viewMenuOpen}
				/>
			{:else}
				<button
					type="button"
					class="ct-toolbar-button ct-icon-button"
					aria-label={t.viewSettings}
					title={t.viewSettings}
					aria-haspopup="menu"
					onpointerenter={() => loadViewMenu()}
					onfocus={() => loadViewMenu()}
					onclick={() => loadViewMenu(true)}
				>
					<Settings2 class="size-4" aria-hidden="true" />
				</button>
			{/if}
		</div>
	</div>

	{#if notice}<p class="ct-library-notice" role="status">{notice}</p>{/if}

	{#if cards.length}
		{#if screen.layout === 'table'}
			<!-- The table loads with the table layout only (bundle budget). -->
			{#await import('#lib/library/LibraryTable.svelte')}
				<div class="ct-library-table-pending" aria-busy="true"></div>
			{:then { default: LibraryTable }}
				<LibraryTable
					columns={screen.columns}
					{cards}
					{selecting}
					{selected}
					ontoggle={toggleSelected}
					ongenre={(genre) => change({ genre })}
				/>
			{/await}
		{:else}
			<div class="ct-library-grid">
				{#each cards as card (card.key)}
					<LibraryCard
						{card}
						lists={screen.bulk?.lists ?? []}
						{selecting}
						selected={selected.includes(card.key)}
						ontoggle={toggleSelected}
						onnotice={(message) => (notice = message)}
					/>
				{/each}
			</div>
		{/if}
		{#if current.hasNext}
			<div class="ct-library-more" use:revealed role="status">
				{loadFailed ? t.loadMoreFailed : t.loadingMore}
			</div>
		{/if}
		{#if selecting && screen.bulk}
			{#await import('#lib/library/BulkBar.svelte') then { default: BulkBar }}
				<BulkBar bulk={screen.bulk} {selected} onclear={() => (selection = { for: listKey, ids: [] })} ondone={bulkDone} />
			{/await}
		{/if}
	{:else}
		<p class="rounded-ct-md bg-surface px-4 py-16 text-center text-muted">
			{t.libraryNoMatch(screen.title)}
		</p>
	{/if}
</main>
