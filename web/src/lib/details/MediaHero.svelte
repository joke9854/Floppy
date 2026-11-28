<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/styles/cards.css';
	import '#lib/details/details.css';
	import './media.css';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import History from '@lucide/svelte/icons/history';
	import Link from '@lucide/svelte/icons/link';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import type { Snippet } from 'svelte';
	import { invalidateAll } from '$app/navigation';
	import { djangoWrite } from '#lib/csrf.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { libraryHref } from '#lib/shell/nav.ts';
	import { t } from '#lib/strings.ts';
	import { openTrack, type TrackTarget } from '#lib/track/open.svelte.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { dt } from './strings.ts';
	import { detailLink } from './link.ts';
	import { activityLine, type MediaActivity, type MediaLinkSection } from './media.ts';

	/**
	 * The hero of the music and podcast pages (P4-L2): art, title, the activity
	 * line, Track (the web track dialog), History, Sync and the links popover.
	 * Square art for music, a show's cover for podcasts.
	 */
	let {
		title,
		image,
		kind,
		backType,
		meta = [],
		activity,
		status = null,
		track,
		historyUrl = '',
		syncUrl = '',
		links,
		children
	}: {
		title: string;
		image: string;
		kind: string;
		backType: string;
		meta?: string[];
		activity: MediaActivity | null;
		status?: string | null;
		track: TrackTarget;
		historyUrl?: string;
		syncUrl?: string;
		links: MediaLinkSection[];
		children?: Snippet;
	} = $props();

	let linksOpen = $state(false);
	let sessionsOpen = $state(false);
	let syncing = $state(false);
	let problem = $state('');

	async function sync() {
		if (syncing) return;
		syncing = true;
		problem = '';
		try {
			const response = await djangoWrite(syncUrl, 'POST');
			if (!response.ok) throw new Error(String(response.status));
			await invalidateAll();
		} catch {
			problem = dt.syncFailed;
		} finally {
			syncing = false;
		}
	}

	function back(event: MouseEvent) {
		if (history.length > 1 && document.referrer.startsWith(location.origin)) {
			event.preventDefault();
			history.back();
		}
	}

	const line = $derived(activityLine(activity));
	const linkSections = $derived(links.filter((section) => section.links.length));
</script>

<Dialog bind:open={linksOpen} title={dt.links} sheet>
	{#each linkSections as section (section.title)}
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

<a
	class="ct-detail-back ct-glass-control"
	href={libraryHref(backType)}
	onclick={back}
	aria-label={t.back}
>
	<ChevronLeft class="size-5" aria-hidden="true" />
</a>

<div class="ct-detail-hero ct-media-hero">
	<div class="ct-detail-poster ct-media-art">
		<img
			alt={title}
			class="ct-fade-img"
			src={image}
			width="500"
			height="500"
			decoding="async"
			fetchpriority="high"
			use:fadeIn
		/>
	</div>
	<div class="ct-detail-identity">
		<h1 class="ct-detail-title">{title}</h1>
		<p class="ct-detail-meta">
			<span>{kind}</span>
			{#each meta as part (part)}<span>{part}</span>{/each}
			{#if status}<span>{status}</span>{/if}
		</p>
		{#if line}
			<p class="ct-media-activity">
				{#if activity?.sessions_query}
					<button type="button" class="ct-meta-link" onclick={() => (sessionsOpen = true)}>{line}</button>
				{:else}
					{line}
				{/if}
			</p>
		{/if}

		<div class="ct-detail-actions">
			<button
				type="button"
				class="ct-btn-primary"
				title={dt.trackTitle}
				onclick={() => openTrack(track)}
			>
				<SlidersHorizontal class="size-5" aria-hidden="true" />
				<span>{t.track}</span>
			</button>
			{#if historyUrl}
				<a class="ct-btn-quiet" {...detailLink(historyUrl)}>
					<History class="size-4" aria-hidden="true" />
					<span>{dt.history}</span>
				</a>
			{/if}
			{#if syncUrl}
				<button type="button" class="ct-btn-quiet" disabled={syncing} onclick={sync}>
					<RefreshCw class={['size-4', syncing && 'animate-spin']} aria-hidden="true" />
					<span>{syncing ? dt.syncing : dt.sync}</span>
				</button>
			{/if}
			{#if linkSections.length}
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
			{#if problem}<p class="ct-detail-problem" role="alert">{problem}</p>{/if}
		</div>

		{@render children?.()}
	</div>
</div>

{#if sessionsOpen && activity?.sessions_query}
	{#await import('./HeroLazy.svelte') then { default: HeroLazy }}
		<HeroLazy query={activity.sessions_query} onclose={() => (sessionsOpen = false)} />
	{/await}
{/if}
