<script lang="ts">
	import '#lib/styles/cards.css';
	import '#lib/styles/screen.css';
	import '#lib/discover/discover.css';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import Ellipsis from '@lucide/svelte/icons/ellipsis';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';
	import { untrack } from 'svelte';
	import { goto, invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import DiscoverCard from '#lib/discover/DiscoverCard.svelte';
	import Hero from '#lib/discover/Hero.svelte';
	import HiddenView from '#lib/discover/HiddenView.svelte';
	import { dc } from '#lib/discover/strings.ts';
	import {
		actionFields,
		discoverQuery,
		rebuildDone,
		type DiscoverAction,
		type DiscoverScreen
	} from '#lib/discover/types.ts';
	import Row from '#lib/home/Row.svelte';
	import { BASE } from '#lib/paths.ts';
	import type { PageProps } from './$types';

	/**
	 * Discover (P4-G), as the Django page (app/discover.html): the type tabs
	 * with More, the ⋮ menu (Refresh recommendations, Hidden from Discover),
	 * the hero, the rows with each card's Add to Planning and Hide (a toast
	 * with Undo), the rest of the rows once the page reaches its end, and the
	 * Hidden view. While the rows rebuild it polls their cache status and
	 * reloads when they are ready.
	 */
	let { data }: PageProps = $props();
	const screen = $derived(data.screen);
	const hiddenView = $derived(screen.media_type === 'hidden');
	const primary = $derived(screen.options.filter((option) => option.primary));
	const more = $derived(screen.options.filter((option) => !option.primary));
	const moreLabel = $derived(more.find((option) => option.value === screen.media_type)?.label);
	// Changes only with the type or show_more, not when the same rows reload.
	const view = $derived(`${screen.media_type}:${screen.show_more}`);

	let busy = $state('');
	let unhiding = $state<number | null>(null);
	let refreshing = $state(false);
	let refreshedNote = $state(false);
	let toast = $state<{ message: string; undo?: string } | null>(null);
	let loadingMore = $state(false);
	let toastTimer: ReturnType<typeof setTimeout> | undefined;
	let sentinel = $state<HTMLDivElement>();
	let moreMenu = $state<HTMLDetailsElement>();
	let actionsMenu = $state<HTMLDetailsElement>();

	function showToast(message: string, undo?: string) {
		clearTimeout(toastTimer);
		toast = { message, undo };
		toastTimer = setTimeout(() => (toast = null), 8000);
	}

	function closeMenus() {
		if (moreMenu) moreMenu.open = false;
		if (actionsMenu) actionsMenu.open = false;
	}

	function switchMedia(value: string) {
		closeMenus();
		if (value === screen.media_type) return;
		goto(`${BASE}/discover${discoverQuery(value)}`, { reset: value === 'hidden' });
	}

	async function post(fields: Record<string, string>): Promise<{ message?: string; undo_token?: string } | null> {
		try {
			const response = await djangoForm(screen.action_url, fields, { json: true });
			if (!response.ok) throw new Error(String(response.status));
			return await response.json();
		} catch {
			showToast(dc.failed);
			return null;
		}
	}

	async function act(action: 'planning' | 'dismiss', key: string, fields: DiscoverAction) {
		if (busy) return;
		busy = key;
		const body = await post(actionFields(action, fields));
		if (body) {
			await invalidate('floppy:discover');
			showToast(body.message ?? '', body.undo_token);
		}
		busy = '';
	}

	async function undo(token: string) {
		clearTimeout(toastTimer);
		toast = null;
		const body = await post({
			action: 'undo',
			undo_token: token,
			active_media_type: screen.media_type,
			show_more: screen.show_more ? '1' : '0',
			discover_debug: '0'
		});
		if (body) {
			await invalidate('floppy:discover');
			showToast(body.message ?? '');
		}
	}

	async function unhide(itemId: number) {
		unhiding = itemId;
		try {
			const response = await djangoForm(
				screen.hide_url,
				{ item_id: String(itemId), action: 'unhide' },
				{ json: true }
			);
			if (!response.ok) throw new Error(String(response.status));
			const body = await response.json();
			await invalidate('floppy:discover');
			showToast(body.message ?? '');
		} catch {
			showToast(dc.failed);
		}
		unhiding = null;
	}

	// Bumped when the page leaves this type or view: a wait still running stops.
	let watchGeneration = 0;

	/**
	 * Polls the rows' cache status (the page's CacheUpdater) until `done`;
	 * false when it gave up, the status failed, or the page moved on.
	 */
	async function waitForRows(showMore: boolean, manual: boolean): Promise<boolean> {
		const generation = watchGeneration;
		const params = new URLSearchParams({
			cache_type: 'discover',
			media_type: screen.media_type,
			show_more: showMore ? '1' : '0'
		});
		for (let attempt = 0; attempt < 60; attempt++) {
			await new Promise((resolve) => setTimeout(resolve, 3000));
			if (generation !== watchGeneration) return false;
			try {
				const response = await fetch(`${screen.status_url}?${params}`, { credentials: 'same-origin' });
				if (!response.ok) return false;
				if (rebuildDone(await response.json(), manual)) return generation === watchGeneration;
			} catch {
				return false;
			}
		}
		return false;
	}

	/** Waits for the rows' rebuild, then reloads them. */
	async function watchRefresh(manual: boolean) {
		refreshing = true;
		const generation = watchGeneration;
		if (await waitForRows(screen.show_more, manual)) {
			await invalidate('floppy:discover');
			if (manual) {
				refreshedNote = true;
				setTimeout(() => (refreshedNote = false), 5000);
			}
		}
		if (generation === watchGeneration) refreshing = false;
	}

	/**
	 * The rest of the rows (show_more). As the page, the rows on screen stay
	 * until the longer tab has rows: when it is still building, wait for it.
	 */
	async function loadMore() {
		if (loadingMore || screen.show_more || hiddenView) return;
		loadingMore = true;
		const generation = watchGeneration;
		const target = `${BASE}/discover${discoverQuery(screen.media_type, true)}`;
		try {
			const response = await fetch(`/api/v1/discover/screen/${discoverQuery(screen.media_type, true)}`, {
				credentials: 'same-origin',
				headers: { accept: 'application/json' }
			});
			const next: DiscoverScreen | null = response.ok ? await response.json() : null;
			const ready = Boolean(next?.rows.length) || (next !== null && (await waitForRows(true, false)));
			if (ready && generation === watchGeneration) await goto(target, { replace: true, reset: false });
		} catch {
			// The rows on screen stay; the next scroll to the end tries again.
		}
		loadingMore = false;
	}

	async function refresh() {
		closeMenus();
		if (refreshing) return;
		try {
			const response = await djangoForm(screen.refresh_url, {
				media_type: screen.media_type,
				show_more: screen.show_more ? '1' : '0'
			});
			if (!response.ok) throw new Error(String(response.status));
		} catch {
			showToast(dc.failed);
			return;
		}
		watchRefresh(true);
	}

	$effect(() => {
		// A wait for this type's rows ends when the page shows another type
		// or view, or closes.
		void view;
		return () => {
			watchGeneration++;
			refreshing = false;
		};
	});

	$effect(() => {
		// The rows are rebuilding in the background (the page's "Building
		// Discover rows"): reload them once they are ready.
		if (screen.loading && !untrack(() => refreshing)) watchRefresh(false);
	});

	$effect(() => {
		// Reaching the end of the rows loads the rest (show_more), as the page does.
		if (!sentinel || screen.show_more || hiddenView || !screen.rows.length) return;
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((entry) => entry.isIntersecting)) loadMore();
			},
			{ rootMargin: '400px 0px' }
		);
		observer.observe(sentinel);
		return () => observer.disconnect();
	});
</script>

<svelte:head><title>Discover - Floppy</title></svelte:head>

<main class="ct-discover mx-auto max-w-[1400px] px-5 pt-6 md:px-8 md:pt-8">
	{#if hiddenView}
		<HiddenView {screen} busy={unhiding} onback={() => switchMedia('all')} onunhide={unhide} />
	{:else}
		<div class="ct-discover-head">
			<div class="ct-page-head">
				<h1 class="ct-page-title">{dc.title}</h1>
				<a href="/search" class="ct-discover-search" aria-label={dc.search} data-sveltekit-reload>
					<Search class="size-5" aria-hidden="true" />
				</a>
			</div>
			<div class="ct-discover-tools">
				<div class="ct-type-switch" role="group" aria-label={dc.mediaType}>
					{#each primary as option (option.value)}
						<button
							type="button"
							class="ct-type-pill"
							aria-pressed={screen.media_type === option.value}
							onclick={() => switchMedia(option.value)}
						>
							{option.label}
						</button>
					{/each}
					{#if more.length}
						<details class="ct-discover-menu" bind:this={moreMenu} ontoggle={() => moreMenu?.open && actionsMenu && (actionsMenu.open = false)}>
							<summary class="ct-type-pill" aria-pressed={Boolean(moreLabel)}>
								{moreLabel ?? dc.more}
								<ChevronDown class="size-4" aria-hidden="true" />
							</summary>
							<div class="ct-discover-menu__panel" role="menu">
								{#each more as option (option.value)}
									<button
										type="button"
										class="ct-discover-menu__item"
										role="menuitem"
										aria-current={screen.media_type === option.value ? 'page' : undefined}
										onclick={() => switchMedia(option.value)}
									>
										{option.label}
									</button>
								{/each}
							</div>
						</details>
					{/if}
				</div>
				<details class="ct-discover-menu" bind:this={actionsMenu} ontoggle={() => actionsMenu?.open && moreMenu && (moreMenu.open = false)}>
					<summary class="ct-discover-actions" aria-label={dc.moreActions} title={dc.moreActions}>
						<Ellipsis class="size-5" aria-hidden="true" />
					</summary>
					<div class="ct-discover-menu__panel" role="menu">
						<button type="button" class="ct-discover-menu__item" role="menuitem" disabled={refreshing} onclick={refresh}>
							<RefreshCw class={['size-5', refreshing && 'ct-discover-spin']} aria-hidden="true" />
							{dc.refresh}
						</button>
						<button type="button" class="ct-discover-menu__item" role="menuitem" onclick={() => switchMedia('hidden')}>
							<EyeOff class="size-5" aria-hidden="true" />
							{dc.hiddenTitle}
							{#if screen.hidden_count}<span class="ct-discover-menu__count">{screen.hidden_count}</span>{/if}
						</button>
					</div>
				</details>
			</div>
		</div>

		{#if refreshing && screen.rows.length}
			<p class="ct-discover-banner">{dc.refreshing}</p>
		{/if}
		{#if refreshedNote}
			<p class="ct-discover-banner is-done" role="status">{dc.refreshed}</p>
		{/if}

		{#if screen.rows.length}
			{#if screen.hero.length}
				<Hero slides={screen.hero} {busy} onplan={(slide) => act('planning', slide.key, slide.action)} />
			{/if}
			<div class="ct-discover-rows">
				<!-- All repeats row keys (one Trending Right Now per type): rows go by position. -->
				{#each screen.rows as row, index}
					<section aria-labelledby="discover-row-{index}">
						<h2 class="ct-discover-row-title" id="discover-row-{index}">{row.title}</h2>
						{#if row.cards.length}
							<Row labelledby="discover-row-{index}">
								{#each row.cards as card, position (position)}
									<DiscoverCard
										{card}
										square={row.square}
										busy={busy === `${index}:${card.key}`}
										onaction={(action, target) => act(action, `${index}:${target.key}`, target.action)}
									/>
								{/each}
							</Row>
						{:else}
							<p class="ct-discover-row-empty">{row.empty_message}</p>
						{/if}
					</section>
				{/each}
			</div>
			{#if !screen.show_more}
				<div bind:this={sentinel} class="ct-discover-more" aria-live="polite">
					{#if loadingMore}{dc.loadingMore}{/if}
				</div>
			{/if}
		{:else if screen.loading || refreshing}
			<div class="ct-discover-empty is-loading">
				<h2>{dc.buildingTitle}</h2>
				<p>{dc.buildingBody}</p>
			</div>
		{:else}
			<div class="ct-discover-empty">
				<h2>{dc.emptyTitle}</h2>
				<p>{dc.emptyBody}</p>
			</div>
		{/if}
	{/if}
</main>

{#if toast}
	<div class="ct-discover-toast" role="status">
		<p>{toast.message}</p>
		{#if toast.undo}
			{@const token = toast.undo}
			<button type="button" class="ct-discover-toast__undo" onclick={() => undo(token)}>{dc.undo}</button>
		{/if}
		<button type="button" class="ct-discover-toast__close" aria-label={dc.dismiss} onclick={() => (toast = null)}>
			<X class="size-4" aria-hidden="true" />
		</button>
	</div>
{/if}
