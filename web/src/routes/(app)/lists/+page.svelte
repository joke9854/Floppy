<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/lists/lists.css';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import Search from '@lucide/svelte/icons/search';
	import { goto, invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import { BASE } from '#lib/paths.ts';
	import ListCard from '#lib/lists/ListCard.svelte';
	import { ls } from '#lib/lists/strings.ts';
	import { listsQuery, sortDirection, type ListCard as Card, type ListsScreen } from '#lib/lists/types.ts';
	import type { PageProps } from './$types';

	/**
	 * Lists (P4-I1), as the Django page (lists/custom_lists.html): New List
	 * with its menu (new list, new smart list, the imports, the public
	 * profile), My Lists / Shared with Me, search, type and sort, the cards
	 * with more loading at the end, and the create, edit and import dialogs.
	 * A list's own page is still Django's until P4-I2.
	 */
	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	// The next pages, loaded as the grid reaches its end (the page's revealed).
	// Cards loaded past the first page; a new page of data (a filter, a sort)
	// clears them in the same update, so keyed rows never repeat.
	let extra = $derived.by((): Card[] => {
		void screen;
		return [];
	});
	let nextPage = $derived(screen.has_next ? screen.page + 1 : 0);
	const cards = $derived([...screen.cards, ...extra]);
	let loadingMore = $state(false);
	let sentinel = $state<HTMLDivElement>();
	let actionsMenu = $state<HTMLDetailsElement>();
	let sortMenu = $state<HTMLDetailsElement>();
	let search = $derived(screen.q);
	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	// The dialogs load when first opened.
	let formOpen = $state(false);
	let formList = $state<number | null>(null);
	let formSmart = $state(false);
	let importKind = $state<'csv' | 'mdblist' | 'trakt' | null>(null);
	const listForm = () => import('#lib/lists/ListForm.svelte');
	const importDialog = () => import('#lib/lists/ImportDialog.svelte');
	let formLoaded = $state(false);
	let importLoaded = $state(false);


	function go(changes: Record<string, string | null>) {
		goto(`${BASE}/lists${listsQuery(page.url.searchParams, changes)}`, { reset: false });
	}

	function onSearch(value: string) {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => go({ q: value || null }), 300);
	}

	function pickSort(value: string) {
		if (sortMenu) sortMenu.open = false;
		go({ sort: value, direction: sortDirection(value, screen.sort, screen.direction) });
	}

	function openForm(listId: number | null, smart = false) {
		if (actionsMenu) actionsMenu.open = false;
		formList = listId;
		formSmart = smart;
		formLoaded = true;
		formOpen = true;
	}

	function openImport(kind: 'csv' | 'mdblist' | 'trakt') {
		if (actionsMenu) actionsMenu.open = false;
		importLoaded = true;
		importKind = kind;
	}

	async function loadMore() {
		if (loadingMore || !nextPage) return;
		loadingMore = true;
		try {
			const query = listsQuery(page.url.searchParams);
			const response = await fetch(`/api/v1/lists/screen/${query}${query ? '&' : '?'}page=${nextPage}`, {
				credentials: 'same-origin',
				headers: { accept: 'application/json' }
			});
			if (response.ok) {
				const next: ListsScreen = await response.json();
				// A page that arrives after the filters changed belongs to the old view.
				if (listsQuery(page.url.searchParams) !== query) return;
				const shown = new Set(cards.map((card) => card.id));
				extra = [...extra, ...next.cards.filter((card) => !shown.has(card.id))];
				nextPage = next.has_next ? next.page + 1 : 0;
			}
		} finally {
			loadingMore = false;
		}
	}

	$effect(() => {
		if (!sentinel || !nextPage) return;
		const observer = new IntersectionObserver((entries) => {
			if (entries.some((entry) => entry.isIntersecting)) loadMore();
		}, { rootMargin: '400px 0px' });
		observer.observe(sentinel);
		return () => observer.disconnect();
	});

	async function saved(location: string | null) {
		// A new smart list opens its rules on the list's (Django) page.
		if (location) window.location.assign(location);
		else await invalidate('floppy:lists');
	}

	const sortLabel = $derived(screen.sorts.find((sort) => sort.value === screen.sort)?.label ?? '');
	const total = $derived(screen.owned_count);
</script>

<svelte:head><title>Lists - Floppy</title></svelte:head>

<main class="ct-lists mx-auto max-w-[1400px] px-5 pt-6 md:px-8 md:pt-8">
	<header class="ct-lists-head">
		<div>
			<h1 class="ct-page-title">{ls.title}</h1>
			<p class="ct-page-sub">
				{ls.count(total)}{#if screen.shared_count} · {ls.sharedWithYou(screen.shared_count)}{/if}
			</p>
		</div>
		<div class="ct-lists-split">
			<button type="button" class="ct-lists-button is-primary" onclick={() => openForm(null)}>{ls.newList}</button>
			<details class="ct-lists-menu" bind:this={actionsMenu}>
				<summary class="ct-lists-button is-primary is-icon" aria-label={ls.moreActions} title={ls.moreActions}>
					<ChevronDown class="size-4" aria-hidden="true" />
				</summary>
				<div class="ct-lists-menu__panel">
					<button type="button" onclick={() => openForm(null)}>{ls.newListItem}</button>
					<button type="button" onclick={() => openForm(null, true)}>{ls.newSmartList}</button>
					<button type="button" onclick={() => openImport('trakt')}>{ls.importTrakt}</button>
					<button type="button" onclick={() => openImport('mdblist')}>{ls.importMdblist}</button>
					<button type="button" onclick={() => openImport('csv')}>{ls.importCsv}</button>
					<a href={screen.urls.profile} data-sveltekit-reload>{ls.publicProfile}</a>
				</div>
			</details>
		</div>
	</header>

	{#if screen.shared_count || screen.scope === 'shared'}
		<div class="ct-status-tabs" role="group">
			<button type="button" class="ct-status-tab" aria-pressed={screen.scope === 'mine'} onclick={() => go({ scope: null })}>
				{ls.myLists}
			</button>
			<button type="button" class="ct-status-tab" aria-pressed={screen.scope === 'shared'} onclick={() => go({ scope: 'shared' })}>
				{ls.sharedWithMe}
			</button>
		</div>
	{/if}

	{#if screen.show_toolbar}
		<div class="ct-lists-toolbar">
			<label class="ct-lists-search">
				<Search class="size-4" aria-hidden="true" />
				<input
					type="search"
					placeholder={ls.search}
					aria-label={ls.search}
					bind:value={search}
					oninput={(event) => onSearch(event.currentTarget.value)}
				/>
			</label>
			<select
				class="ct-lists-select"
				aria-label={ls.type}
				value={screen.media_type}
				onchange={(event) => go({ media_type: event.currentTarget.value === 'all' ? null : event.currentTarget.value })}
			>
				{#each screen.media_types as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
			</select>
			<details class="ct-lists-menu" bind:this={sortMenu}>
				<summary class="ct-lists-button">
					{sortLabel}
					<span aria-hidden="true">{screen.direction === 'asc' ? '↑' : '↓'}</span>
				</summary>
				<div class="ct-lists-menu__panel">
					{#each screen.sorts as option (option.value)}
						<button type="button" aria-current={screen.sort === option.value ? 'true' : undefined} onclick={() => pickSort(option.value)}>
							{option.label}
						</button>
					{/each}
				</div>
			</details>
		</div>
	{/if}

	{#if cards.length}
		<div class="ct-lists-grid">
			{#each cards as card (card.id)}
				<ListCard {card} onedit={(target) => openForm(target.id)} />
			{/each}
		</div>
		{#if nextPage}
			<div bind:this={sentinel} class="ct-lists-more" aria-live="polite">{#if loadingMore}{ls.loadingMore}{/if}</div>
		{/if}
	{:else if screen.q || screen.media_type !== 'all' || screen.scope === 'shared'}
		<p class="ct-lists-none">{ls.noMatches}</p>
	{:else}
		<section class="ct-lists-empty">
			<h2>{ls.emptyTitle}</h2>
			<p>{ls.emptyBody}</p>
			<button type="button" class="ct-lists-button is-primary" onclick={() => openForm(null)}>{ls.emptyAction}</button>
		</section>
	{/if}
</main>

{#if formLoaded}
	{#await listForm() then { default: ListForm }}
		<ListForm bind:open={formOpen} listId={formList} smart={formSmart} {screen} onsaved={saved} />
	{/await}
{/if}
{#if importLoaded}
	{#await importDialog() then { default: ImportDialog }}
		<ImportDialog bind:kind={importKind} {screen} />
	{/await}
{/if}
