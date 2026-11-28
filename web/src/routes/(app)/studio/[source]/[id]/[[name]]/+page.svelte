<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/styles/cards.css';
	import '#lib/details/details.css';
	import '#lib/details/pages.css';
	import Check from '@lucide/svelte/icons/check';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { detailLink } from '#lib/details/link.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { BASE } from '#lib/paths.ts';
	import { t } from '#lib/strings.ts';
	import { dt } from '#lib/details/strings.ts';
	import { ls } from '#lib/details/lazyStrings.ts';
	import type { PageProps } from './$types';

	/**
	 * The studio page (studio_detail.html): the logo, name, your numbers, the
	 * website and the description, then the titles it credits as poster cards
	 * with your status. The person page's components and styles.
	 */
	let { data }: PageProps = $props();
	const studio = $derived(data.studio.studio);

	let bioOpen = $state(false);

	function back(event: MouseEvent) {
		if (history.length > 1 && document.referrer.startsWith(location.origin)) {
			event.preventDefault();
			history.back();
		}
	}
</script>

<svelte:head>
	<title>{studio.name} · Floppy</title>
</svelte:head>

<main class="ct-detail">
	<div class="mx-auto max-w-[1400px] px-5 md:px-8">
		<a class="ct-detail-back ct-glass-control" href="{BASE}/" onclick={back} aria-label={t.back}>
			<ChevronLeft class="size-5" aria-hidden="true" />
		</a>

		<div class="ct-detail-hero">
			{#if studio.image}
				<div class="ct-detail-poster">
					<img
						alt={studio.name}
						class="ct-fade-img"
						src={studio.image}
						width="500"
						height="500"
						decoding="async"
						fetchpriority="high"
						use:fadeIn
					/>
				</div>
			{/if}
			<div class="ct-detail-identity">
				<h1 class="ct-detail-title">{studio.name}</h1>
				<p class="ct-detail-meta">
					<span>{studio.source_label}</span>
					{#if studio.founded}<span>{ls.founded(studio.founded)}</span>{/if}
				</p>
				<p class="ct-person-stats">
					{#each studio.counts as count (count.label)}
						<span>{count.label}: {count.value}</span>
					{/each}
				</p>
				{#if studio.source_url}
					<div class="ct-detail-actions">
						<a class="ct-btn-quiet" href={studio.source_url} target="_blank" rel="noopener noreferrer">
							<span>{ls.website}</span>
							<ExternalLink class="size-4" aria-hidden="true" />
						</a>
					</div>
				{/if}
				{#if studio.description}
					<div class="ct-person-bio">
						<p class:is-clamped={!bioOpen}>{studio.description}</p>
						<button type="button" class="ct-row-link" onclick={() => (bioOpen = !bioOpen)}>
							{bioOpen ? dt.showLess : dt.readMore}
						</button>
					</div>
				{/if}
			</div>
		</div>

		<div class="ct-detail-sections">
			{#each data.studio.sections as section, s (s)}
				<section aria-labelledby="ct-studio-{s}">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-studio-{s}">{section.label}</h2>
					</div>
					{#if section.cards.length}
						<div class="ct-studio-grid">
							{#each section.cards as entry, index (index)}
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
												<span class="ct-credit-badge" aria-label={dt.watched}><Check class="size-3.5" /></span>
											{/if}
										</span>
										<span class="ct-poster-title">{entry.title}</span>
										<span class="ct-poster-sub">{entry.status ?? entry.year}</span>
									</a>
								</article>
							{/each}
						</div>
					{:else}
						<p class="ct-person-stats">{ls.noTitles}</p>
					{/if}
				</section>
			{/each}
		</div>
	</div>
</main>

<style>
	.ct-studio-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: 16px;
	}
</style>
