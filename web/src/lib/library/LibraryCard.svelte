<script lang="ts">
	import Ellipsis from '@lucide/svelte/icons/ellipsis';
	import type { Component } from 'svelte';
	import { detailLink } from '#lib/details/link.ts';
	import type { components } from '#lib/api/client.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { STATUS_LOOKS } from '#lib/media/status.ts';
	import { t } from '#lib/strings.ts';
	import { lazyComponent } from './lazy.ts';

	type Card = components['schemas']['LibraryCard'];
	type Choice = { value: string; label: string };

	/**
	 * A Library card (A3): the crisp poster (square for music and podcasts)
	 * with a status badge and an inset progress line, then the title, the
	 * subtitle ("S2 E5 next" or the status) and the value the list is sorted
	 * by. B5 adds the card's menu (Track, Add to list, History, as the page's
	 * hover buttons) and the Next ep pill; in Select mode a tap selects.
	 */
	let {
		card,
		lists = [],
		selecting = false,
		selected = false,
		ontoggle,
		onnotice
	}: {
		card: Card;
		lists?: Choice[];
		selecting?: boolean;
		selected?: boolean;
		ontoggle?: (key: number) => void;
		onnotice?: (message: string) => void;
	} = $props();

	const look = $derived(card.status ? STATUS_LOOKS[card.status] : undefined);

	type MenuProps = {
		title: string;
		mediaType: string;
		url: string;
		historyUrl: string;
		lists: Choice[];
		itemId: number;
		onnotice?: (message: string) => void;
		initialOpen?: boolean;
	};
	let Menu = $state<Component<MenuProps> | null>(null);
	let openOnLoad = $state(false);
	function loadMenu(open = false) {
		if (open) openOnLoad = true;
		lazyComponent<MenuProps>('card-menu', () => import('./CardMenu.svelte')).then((menu) => {
			Menu = menu;
		});
	}
</script>

<article
	class={['ct-library-card', selecting && 'is-selecting', selected && 'is-selected']}
	data-media-type={card.media_type}
	data-shape={card.shape}
>
	{#if selecting}
		<button type="button" class="ct-library-select" aria-pressed={selected} onclick={() => ontoggle?.(card.key)}>
			<span class="ct-library-poster">
				<img alt="" src={card.poster} loading="lazy" decoding="async" />
				<span class="ct-select-mark" aria-hidden="true"></span>
			</span>
			<span class="ct-library-title">{card.title}</span>
		</button>
	{:else}
		<a {...detailLink(card.url)}>
			<span class="ct-library-poster">
				<img
					alt={card.title}
					class="ct-fade-img"
					src={card.poster}
					srcset={card.poster_srcset || undefined}
					sizes={card.poster_srcset ? '(min-width: 30rem) 170px, 33vw' : undefined}
					width="342"
					height={card.shape === 'square' ? 342 : 513}
					loading="lazy"
					decoding="async"
					use:fadeIn
				/>
				{#if card.progress}
					<span class={['ct-library-progress', card.progress.paused && 'is-paused']} aria-hidden="true">
						<span style:width="{card.progress.percent}%"></span>
					</span>
				{/if}
			</span>
			<span class="ct-library-title">{card.title}</span>
			<span class="ct-library-sub">{card.subtitle}</span>
			{#if card.detail}<span class="ct-library-detail">{card.detail}</span>{/if}
		</a>
		{#if card.next_episode_url}
			<a class="ct-next-ep" {...detailLink(card.next_episode_url)} title={t.jumpToNextEpisode}>
				{t.nextEp}
			</a>
		{/if}
		{#if Menu}
			<Menu
				title={card.title}
				mediaType={card.media_type}
				url={card.url}
				historyUrl={card.history_url}
				{lists}
				itemId={card.key}
				{onnotice}
				initialOpen={openOnLoad}
			/>
		{:else}
			<button
				type="button"
				class="ct-card-menu"
				aria-label={t.cardActions(card.title)}
				aria-haspopup="menu"
				onpointerenter={() => loadMenu()}
				onfocus={() => loadMenu()}
				onclick={() => loadMenu(true)}
			>
				<Ellipsis class="size-4" aria-hidden="true" />
			</button>
		{/if}
	{/if}
	{#if look}
		<span class="ct-status-badge" data-status={look.slug} title={card.status}>
			<look.icon class="size-[13px]" strokeWidth={2.5} aria-hidden="true" />
			<span class="sr-only">{card.status}</span>
		</span>
	{/if}
</article>
