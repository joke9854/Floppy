<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/styles/cards.css';
	import '#lib/details/details.css';
	import '#lib/details/pages.css';
	import Check from '@lucide/svelte/icons/check';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import History from '@lucide/svelte/icons/history';
	import { detailLink } from '#lib/details/link.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { BASE } from '#lib/paths.ts';
	import { t } from '#lib/strings.ts';
	import type { PageProps } from './$types';

	/**
	 * The person page (ct/person_page.html): the portrait, name, role · born
	 * · birthplace, your numbers with them, History and the source's page, the
	 * biography; then what you have watched, Known For, and the filmography
	 * as one list (All / Movies / Shows, newest or oldest first, the first 20
	 * until "All N credits").
	 */
	let { data }: PageProps = $props();
	const person = $derived(data.person);

	let bioOpen = $state(false);
	let type = $state<'all' | 'movie' | 'tv'>('all');
	let oldest = $state(false);
	let showAll = $state(false);
	const credits = $derived.by(() => {
		const list = person.filmography.filter((credit) => type === 'all' || credit.media_type === type);
		const ordered = oldest ? [...list].reverse() : list;
		return type === 'all' && !showAll ? ordered.slice(0, 20) : ordered;
	});
	const hasTypes = $derived(!person.is_author && person.stats.movies !== null);

	function back(event: MouseEvent) {
		if (history.length > 1 && document.referrer.startsWith(location.origin)) {
			event.preventDefault();
			history.back();
		}
	}
</script>

<svelte:head>
	<title>{person.name} · Floppy</title>
</svelte:head>

{#snippet card(entry: PageProps['data']['person']['watched'][number])}
	<article class="ct-poster-card">
		<a {...detailLink(entry.url)} class="ct-poster-link">
			<span class="ct-poster-frame">
				<img
					alt={entry.title}
					class="ct-poster-img ct-fade-img"
					src={entry.poster}
					width="342"
					height="513"
					loading="lazy"
					decoding="async"
					use:fadeIn
				/>
				{#if entry.watched}
					<span class="ct-credit-badge" aria-label={t.watched}><Check class="size-3.5" /></span>
				{/if}
			</span>
			<span class="ct-poster-title">{entry.title}</span>
			<span class="ct-poster-sub">{entry.year}</span>
		</a>
	</article>
{/snippet}

<main class="ct-detail">
	<div class="mx-auto max-w-[1400px] px-5 md:px-8">
		<a class="ct-detail-back ct-glass-control" href="{BASE}/" onclick={back} aria-label={t.back}>
			<ChevronLeft class="size-5" aria-hidden="true" />
		</a>

		<div class="ct-detail-hero">
			<div class="ct-detail-poster">
				<img
					alt={person.name}
					class="ct-fade-img"
					src={person.image}
					width="500"
					height="750"
					decoding="async"
					fetchpriority="high"
					use:fadeIn
				/>
			</div>
			<div class="ct-detail-identity">
				<h1 class="ct-detail-title">{person.name}</h1>
				<p class="ct-detail-meta">
					{#if person.department}<span>{person.department}</span>{/if}
					{#if person.born}<span>{person.born}</span>{/if}
					{#if person.place_of_birth}<span>{person.place_of_birth}</span>{/if}
				</p>
				{#if person.watched.length}
					<p class="ct-person-stats">
						<span>{t.titlesWatched(person.stats.titles)}</span>
						{#if person.is_author}
							{#if person.stats.books}<span>{t.booksRead(person.stats.books)}</span>{/if}
						{:else}
							{#if person.stats.movies}<span>{t.moviesCount(person.stats.movies)}</span>{/if}
							{#if person.stats.shows}<span>{t.showsCount(person.stats.shows)}</span>{/if}
							{#if person.stats.together}<span>{t.together(person.stats.together)}</span>{/if}
						{/if}
					</p>
				{/if}
				<div class="ct-detail-actions">
					{#if person.history_url}
						<a class="ct-btn-quiet" href={person.history_url} data-sveltekit-reload>
							<History class="size-4" aria-hidden="true" />
							<span>{t.viewInHistory}</span>
						</a>
					{/if}
					{#if person.source_url}
						<a class="ct-btn-quiet" href={person.source_url} target="_blank" rel="noopener noreferrer">
							<span>{person.source_label}</span>
							<ExternalLink class="size-4" aria-hidden="true" />
						</a>
					{/if}
				</div>
				{#if person.biography}
					<div class="ct-person-bio">
						<p class:is-clamped={!bioOpen}>{person.biography}</p>
						<button type="button" class="ct-row-link" onclick={() => (bioOpen = !bioOpen)}>
							{bioOpen ? t.showLess : t.readMore}
						</button>
					</div>
				{/if}
			</div>
		</div>

		<div class="ct-detail-sections">
			{#if person.watched.length}
				<section aria-labelledby="ct-watched-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-watched-title">
							{person.is_author ? t.youveRead : t.youveWatched}
						</h2>
					</div>
					<div class="ct-detail-rail">
						{#each person.watched as entry, index (index)}{@render card(entry)}{/each}
					</div>
				</section>
			{/if}

			{#if person.known_for.length}
				<section aria-labelledby="ct-known-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-known-title">{t.knownFor}</h2>
					</div>
					<div class="ct-detail-rail">
						{#each person.known_for as entry, index (index)}{@render card(entry)}{/each}
					</div>
				</section>
			{/if}

			{#if person.filmography.length}
				<section aria-labelledby="ct-filmography-title">
					<div class="ct-row-head ct-title-toggle" role="tablist">
						<h2 class="ct-row-title" id="ct-filmography-title">
							{person.is_author ? t.bibliography : t.filmography}
						</h2>
						{#if hasTypes}
							{#each [['all', t.all], ['movie', t.movies], ['tv', t.shows]] as const as [key, label] (key)}
								<button
									type="button"
									role="tab"
									class={['ct-row-title', type !== key && 'is-off']}
									aria-selected={type === key}
									onclick={() => (type = key)}>{label}</button
								>
							{/each}
						{/if}
						<button type="button" class="ct-row-link ct-filmography__sort" onclick={() => (oldest = !oldest)}>
							{oldest ? t.oldestFirst : t.newestFirst}
						</button>
					</div>
					<ol class="ct-filmography__list">
						{#each credits as credit, index (index)}
							<li class="ct-credit">
								<a {...detailLink(credit.url)} class="ct-credit__link">
									<img
										alt=""
										class="ct-credit__thumb ct-fade-img"
										src={credit.thumb}
										width="40"
										height="60"
										loading="lazy"
										decoding="async"
										use:fadeIn
									/>
									<span class="ct-credit__year">{credit.year || '—'}</span>
									<span class="ct-credit__text">
										<span class="ct-credit__title">{credit.title}</span>
										<span class="ct-credit__role"
											>{credit.role ? `${credit.role} · ` : ''}{credit.type_label}{credit.departments
												.length
												? ` · ${credit.departments.join(', ')}`
												: ''}</span
										>
									</span>
									<span
										class={['ct-credit__check', credit.watched && 'is-watched']}
										title={credit.watched ? t.watched : undefined}
									>
										{#if credit.watched}<Check class="size-4" aria-hidden="true" />{/if}
									</span>
								</a>
							</li>
						{/each}
					</ol>
					{#if type === 'all' && !showAll && person.filmography.length > 20}
						<button type="button" class="ct-row-link ct-filmography__more" onclick={() => (showAll = true)}>
							{t.allCredits(person.filmography.length)}
							<ChevronRight class="size-4" aria-hidden="true" />
						</button>
					{/if}
				</section>
			{/if}
		</div>
	</div>
</main>
