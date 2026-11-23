<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/library/library.css';
	import '#lib/lists/lists.css';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import LayoutGrid from '@lucide/svelte/icons/layout-grid';
	import TableIcon from '@lucide/svelte/icons/table-2';
	import { goto, invalidate } from '$app/navigation';
	import { page as appPage } from '$app/state';
	import { djangoForm } from '#lib/csrf.ts';
	import ColumnMenu from '#lib/library/LazyColumnMenu.svelte';
	import type { LibraryCard as Card } from '#lib/library/query.ts';
	import { ld } from '#lib/lists/strings.ts';
	import { listPageQuery, sortDirection, toggleValue, type ListsScreen } from '#lib/lists/types.ts';
	import { BASE } from '#lib/paths.ts';
	import type { ListPage } from './+page.server.ts';
	import type { PageProps } from './$types';

	/**
	 * A manual list's page (P4-I2), as the Django page (lists/list_detail.html)
	 * for its editors: the header with completion, the Public chip and Links,
	 * collaborators, the type breakdown; Add New Item and the list menu; search,
	 * type, status, sort, grid or table with its columns, custom order with
	 * the move buttons, select mode with the Library's bulk bar, and more items
	 * on scroll. Add item, recommendations, activity and export are the Django
	 * pages.
	 */
	let { data }: PageProps = $props();
	const screen = $derived(data.page);
	const list = $derived(screen.list!);
	const reference = $derived(appPage.params.ref ?? '');
	const here = $derived(`${BASE}/list/${encodeURIComponent(reference)}`);
	const withNext = (url: string) => `${url}?next=${encodeURIComponent(here)}`;

	// Pages fetched again before a refresh (a move, a bulk action), handed to
	// the new data in the same update so the grid keeps its length and scroll.
	let carry: { cards: Card[]; next: number; last: number } | null = null;
	const carried = $derived.by(() => {
		void screen;
		const pages = carry;
		carry = null;
		return pages;
	});
	// Cards loaded past the first page; a new page of data (a filter, a sort)
	// replaces them in the same update, so keyed rows never repeat.
	let extra = $derived.by((): Card[] => {
		const first = new Set((screen.cards ?? []).map((card) => card.key));
		return (carried?.cards ?? []).filter((card) => !first.has(card.key));
	});
	let nextPage = $derived(carried ? carried.next : screen.has_next ? (screen.page ?? 1) + 1 : 0);
	let lastPage = $derived(carried?.last ?? screen.page ?? 1);
	const cards = $derived([...(screen.cards ?? []), ...extra]);
	let loadingMore = $state(false);
	let sentinel = $state<HTMLDivElement>();
	let search = $derived(screen.q ?? '');
	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	let editingOrder = $state(false);
	let moving = $state<number | null>(null);
	let notice = $state('');
	let actionsMenu = $state<HTMLDetailsElement>();
	let sortMenu = $state<HTMLDetailsElement>();
	let selecting = $state(false);
	let selected = $state<number[]>([]);
	let formOpen = $state(false);
	let formLoaded = $state(false);
	const listForm = () => import('#lib/lists/ListForm.svelte');


	function go(changes: Parameters<typeof listPageQuery>[1]) {
		goto(`${here}${listPageQuery(appPage.url.searchParams, changes)}`, { reset: false });
	}

	function onSearch(value: string) {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => go({ q: value || null }), 300);
	}

	async function fetchPage(query: string, number: number): Promise<ListPage | null> {
		const response = await fetch(
			`/api/v1/lists/page/${encodeURIComponent(reference)}/${query}${query ? '&' : '?'}page=${number}`,
			{ credentials: 'same-origin', headers: { accept: 'application/json' } }
		);
		return response.ok ? ((await response.json()) as ListPage) : null;
	}

	async function loadMore() {
		if (loadingMore || !nextPage) return;
		loadingMore = true;
		const query = listPageQuery(appPage.url.searchParams);
		try {
			const next = await fetchPage(query, nextPage);
			if (!next || listPageQuery(appPage.url.searchParams) !== query) return;
			const shown = new Set(cards.map((card) => card.key));
			extra = [...extra, ...(next.cards ?? []).filter((card) => !shown.has(card.key))];
			nextPage = next.has_next ? (next.page ?? nextPage) + 1 : 0;
			lastPage = next.page ?? nextPage;
		} finally {
			loadingMore = false;
		}
	}

	/** Reload the page's data with every page loaded so far. */
	async function refresh() {
		const query = listPageQuery(appPage.url.searchParams);
		const pages: Card[] = [];
		let next = 0;
		for (let number = 2; number <= lastPage; number += 1) {
			const loaded = await fetchPage(query, number);
			if (!loaded) break;
			pages.push(...(loaded.cards ?? []));
			next = loaded.has_next ? number + 1 : 0;
		}
		carry = lastPage > 1 && pages.length ? { cards: pages, next, last: lastPage } : null;
		await invalidate('floppy:list');
	}

	$effect(() => {
		if (!sentinel || !nextPage) return;
		const observer = new IntersectionObserver((entries) => {
			if (entries.some((entry) => entry.isIntersecting)) loadMore();
		}, { rootMargin: '400px 0px' });
		observer.observe(sentinel);
		return () => observer.disconnect();
	});

	async function move(key: number, action: 'first' | 'back' | 'next' | 'last') {
		moving = key;
		try {
			// The page's move buttons: the whole list is renumbered, so items
			// beyond the loaded page keep their order.
			const response = await djangoForm(screen.urls!.reorder, { item_id: String(key), action });
			if (!response.ok) throw new Error(String(response.status));
			await refresh();
		} catch {
			notice = ld.failed;
		}
		moving = null;
	}

	function toggleSelected(key: number) {
		selected = selected.includes(key) ? selected.filter((id) => id !== key) : [...selected, key];
	}

	async function bulkDone(message: string) {
		selecting = false;
		selected = [];
		notice = message;
		await refresh();
	}

	// The edit dialog takes the index's shape: its urls come from this page.
	const formScreen = $derived({
		urls: {
			create: '',
			edit: screen.urls!.edit,
			delete: screen.urls!.delete,
			edit_form: screen.urls!.edit_form.replace(`/${list.id}/`, '/{id}/'),
			profile: '',
			url_template: screen.urls!.url_template
		},
		tag_options: []
	} as unknown as ListsScreen);

	async function saved(location: string | null) {
		if (location) window.location.assign(location);
		else {
			// A deleted list is gone: back to the index.
			const response = await fetch(`/api/v1/lists/page/${encodeURIComponent(reference)}/`, { credentials: 'same-origin' });
			const next = response.ok ? await response.json() : null;
			if (!next?.handled) goto(`${BASE}/lists`);
			else await invalidate('floppy:list');
		}
	}

	const sortLabel = $derived(screen.sorts?.find((sort) => sort.value === screen.sort)?.label ?? '');
	const statuses = $derived(screen.current_statuses ?? []);
	const types = $derived(screen.current_media_types ?? []);
	const filtering = $derived(Boolean(screen.q) || types.length > 0 || statuses.length > 0);
</script>

<svelte:head><title>{list.name} - Floppy</title></svelte:head>

<main class="ct-lists mx-auto max-w-[1400px] px-5 pt-6 md:px-8 md:pt-8">
	<header class="ct-lists-head">
		<div class="ct-list-page__title">
			<h1 class="ct-page-title">{list.name}</h1>
			<p class="ct-page-sub">
				{ld.items(list.items_count)}
				{#if list.completion_percent !== null && list.completion_percent !== undefined}
					· <span title={ld.completedOf(list.completed_count, list.items_count)}>{ld.complete(list.completion_percent)}</span>
				{/if}
			</p>
			<div class="ct-list-page__chips">
				{#if list.is_public}
					<details class="ct-lists-menu">
						<summary class="ct-chip is-static">{ld.public} · {ld.links} <ChevronDown class="size-3" aria-hidden="true" /></summary>
						<div class="ct-lists-menu__panel is-left">
							{#each list.links as link (link.label)}<a href={link.href} data-sveltekit-reload>{link.label}</a>{/each}
						</div>
					</details>
				{/if}
				{#if list.collaborators_count > 1}<span class="ct-chip is-static">{ld.collaborators(list.collaborators_count)}</span>{/if}
				{#if (screen.breakdown ?? []).length > 1}
					<details class="ct-lists-menu">
						<summary class="ct-chip is-static">{ld.breakdown}</summary>
						<div class="ct-lists-menu__panel is-left ct-list-breakdown">
							{#each screen.breakdown ?? [] as slice (slice.value)}
								<span><i style:background={slice.color}></i>{slice.label}<b>{slice.count} · {slice.percent}%</b></span>
							{/each}
						</div>
					</details>
				{/if}
			</div>
			{#if list.description}<p class="ct-list-page__description">{list.description}</p>{/if}
		</div>
		<div class="ct-lists-split">
			<a class="ct-lists-button is-primary" href={withNext(screen.urls!.add_item)} data-sveltekit-reload>{ld.addItem}</a>
			<details class="ct-lists-menu" bind:this={actionsMenu}>
				<summary class="ct-lists-button is-primary is-icon" aria-label={ld.moreActions} title={ld.moreActions}>
					<ChevronDown class="size-4" aria-hidden="true" />
				</summary>
				<div class="ct-lists-menu__panel">
					<a href={withNext(screen.urls!.add_item)} data-sveltekit-reload>{ld.addItem}</a>
					{#if list.can_recommend}<a href={screen.urls!.recommend} data-sveltekit-reload>{ld.addRecommendation}</a>{/if}
					<button
						type="button"
						onclick={() => {
							if (actionsMenu) actionsMenu.open = false;
							formLoaded = true;
							formOpen = true;
						}}>{ld.editList}</button
					>
					<a href={screen.urls!.activity} data-sveltekit-reload>{ld.activity}</a>
					{#if list.can_recommend && list.recommendation_count > 0}
						<a href={screen.urls!.recommendations} data-sveltekit-reload>{ld.recommendations}</a>
					{/if}
					<a href={screen.urls!.export} data-sveltekit-reload>{ld.exportCsv}</a>
				</div>
			</details>
		</div>
	</header>

	<div class="ct-lists-toolbar">
		<label class="ct-lists-search">
			<input type="search" placeholder={ld.search} aria-label={ld.search} bind:value={search} oninput={(event) => onSearch(event.currentTarget.value)} />
		</label>
		<details class="ct-lists-menu">
			<summary class="ct-lists-button">{ld.type}{#if types.length} ({types.length}){/if}</summary>
			<div class="ct-lists-menu__panel is-left">
				<button type="button" aria-current={types.length === 0 ? 'true' : undefined} onclick={() => go({ type: [] })}>{ld.allTypes}</button>
				{#each screen.media_types ?? [] as option (option.value)}
					<button type="button" aria-current={types.includes(option.value) ? 'true' : undefined} onclick={() => go({ type: toggleValue(types, option.value) })}>
						{option.label}
					</button>
				{/each}
			</div>
		</details>
		<details class="ct-lists-menu">
			<summary class="ct-lists-button">{ld.status}{#if statuses.length} ({statuses.length}){/if}</summary>
			<div class="ct-lists-menu__panel is-left">
				{#each screen.statuses ?? [] as option (option.value)}
					<button
						type="button"
						aria-current={(option.value === 'All' ? statuses.length === 0 : statuses.includes(option.value)) ? 'true' : undefined}
						onclick={() => go({ status: toggleValue(statuses, option.value, 'All') })}
					>
						{option.label}
					</button>
				{/each}
			</div>
		</details>
		<details class="ct-lists-menu" bind:this={sortMenu}>
			<summary class="ct-lists-button">{sortLabel} <span aria-hidden="true">{screen.direction === 'asc' ? '↑' : '↓'}</span></summary>
			<div class="ct-lists-menu__panel">
				{#each screen.sorts ?? [] as option (option.value)}
					<button
						type="button"
						aria-current={screen.sort === option.value ? 'true' : undefined}
						onclick={() => {
							if (sortMenu) sortMenu.open = false;
							go({ sort: option.value, direction: sortDirection(option.value, screen.sort ?? '', screen.direction ?? 'desc') });
						}}
					>
						{option.label}
					</button>
				{/each}
			</div>
		</details>
		{#if screen.ordering}
			<button type="button" class="ct-lists-button" aria-pressed={editingOrder} onclick={() => (editingOrder = !editingOrder)}>
				{editingOrder ? ld.doneOrder : ld.editOrder}
			</button>
		{/if}
		<button
			type="button"
			class="ct-lists-button is-icon"
			title={screen.layout === 'table' ? ld.grid : ld.table}
			aria-label={screen.layout === 'table' ? ld.grid : ld.table}
			onclick={() => go({ layout: screen.layout === 'table' ? 'grid' : 'table' })}
		>
			{#if screen.layout === 'table'}<LayoutGrid class="size-4" aria-hidden="true" />{:else}<TableIcon class="size-4" aria-hidden="true" />{/if}
		</button>
		{#if screen.layout === 'table'}
			<ColumnMenu
				mediaType={screen.column_media_type ?? 'all'}
				sort={screen.sort ?? ''}
				config={screen.column_config ?? []}
				defaults={screen.default_column_config ?? []}
				tableType="list"
			/>
		{/if}
		{#if screen.bulk}
			<button
				type="button"
				class="ct-lists-button"
				onclick={() => {
					selecting = !selecting;
					selected = [];
				}}>{selecting ? ld.cancelSelect : ld.select}</button
			>
		{/if}
	</div>

	{#if filtering}<p class="ct-list-page__summary">{ld.results(list.filtered_count)}</p>{/if}

	{#if cards.length}
		{#if screen.layout === 'table'}
			{#await import('#lib/library/LibraryTable.svelte') then { default: LibraryTable }}
				<LibraryTable
					columns={screen.columns ?? []}
					{cards}
					{selecting}
					{selected}
					ontoggle={toggleSelected}
					ongenre={() => {}}
				/>
			{/await}
		{:else}
			<!-- The card loads with the grid, which keeps the page within its budget. -->
			{#await import('#lib/library/LibraryCard.svelte') then { default: LibraryCard }}
				<div class="ct-library-grid">
					{#each cards as card (card.key)}
						<div class={['ct-list-page__cell', moving === card.key && 'is-busy']}>
							<LibraryCard
								{card}
								lists={screen.bulk?.lists ?? []}
								{selecting}
								selected={selected.includes(card.key)}
								ontoggle={toggleSelected}
								onnotice={(message) => (notice = message)}
							/>
							{#if editingOrder}
								<div class="ct-list-page__move" role="group">
									<button type="button" title={ld.moveFirst} aria-label={ld.moveFirst} onclick={() => move(card.key, 'first')}>⇤</button>
									<button type="button" title={ld.moveBack} aria-label={ld.moveBack} onclick={() => move(card.key, 'back')}>←</button>
									<button type="button" title={ld.moveNext} aria-label={ld.moveNext} onclick={() => move(card.key, 'next')}>→</button>
									<button type="button" title={ld.moveLast} aria-label={ld.moveLast} onclick={() => move(card.key, 'last')}>⇥</button>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/await}
		{/if}
		{#if nextPage}
			<div bind:this={sentinel} class="ct-lists-more" aria-live="polite">{#if loadingMore}{ld.loadingMore}{/if}</div>
		{/if}
		{#if selecting && screen.bulk}
			{#await import('#lib/library/BulkBar.svelte') then { default: BulkBar }}
				<BulkBar bulk={screen.bulk} {selected} onclear={() => (selected = [])} ondone={bulkDone} />
			{/await}
		{/if}
	{:else if filtering}
		<section class="ct-lists-empty">
			<h2>{ld.noResults}</h2>
			{#if screen.q}<p>{ld.noResultsQuery(screen.q)}</p>{/if}
		</section>
	{:else}
		<section class="ct-lists-empty">
			<h2>{ld.empty}</h2>
			<a class="ct-lists-button is-primary" href={withNext(screen.urls!.add_item)} data-sveltekit-reload>{ld.addItem}</a>
		</section>
	{/if}
</main>

{#if notice}<p class="ct-list-page__notice" role="status">{notice}</p>{/if}

{#if formLoaded}
	{#await listForm() then { default: ListForm }}
		<ListForm bind:open={formOpen} listId={list.id} screen={formScreen} onsaved={saved} />
	{/await}
{/if}

