<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import MediaHero from '#lib/details/MediaHero.svelte';
	import {
		playTime,
		podcastApiPath,
		toLocalInput,
		type PodcastEpisode,
		type PodcastEpisodesPage
	} from '#lib/details/media.ts';
	import { genreLink } from '#lib/details/link.ts';
	import { dt } from '#lib/details/strings.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	// The first page of episodes comes with the show; "Show more" appends the next ones.
	let more = $state.raw<{
		for: PageProps['data']['screen'];
		rows: PodcastEpisode[];
		next: number | null | undefined;
		loading: boolean;
		failed: boolean;
	} | null>(null);
	const extra = $derived(
		more?.for === screen
			? more
			: { rows: [] as PodcastEpisode[], next: screen.episodes.next_page, loading: false, failed: false }
	);
	const episodes = $derived([...screen.episodes.episodes, ...extra.rows]);

	async function showMore() {
		const page = extra.next;
		if (!page || extra.loading) return;
		const forScreen = screen;
		more = { for: forScreen, rows: extra.rows, next: page, loading: true, failed: false };
		try {
			const response = await fetch(podcastApiPath(screen.show.source, screen.show.uuid, page), {
				credentials: 'same-origin'
			});
			if (!response.ok) throw new Error(String(response.status));
			const body = (await response.json()) as PodcastEpisodesPage;
			if (screen !== forScreen) return;
			more = {
				for: forScreen,
				rows: [...extra.rows, ...body.episodes],
				next: body.next_page,
				loading: false,
				failed: false
			};
		} catch {
			if (screen === forScreen) {
				more = { for: forScreen, rows: extra.rows, next: page, loading: false, failed: true };
			}
		}
	}

	let descriptionOpen = $state(false);
	const longDescription = $derived(screen.show.description.length > 280);

	// The Plays dialog loads on the first tap (it is not part of the page's first load).
	let playsOpen = $state(false);
	let selected = $state<number | null>(null);
	const episode = $derived(episodes.find((row) => row.id === selected) ?? null);
	const suggestion = $derived(
		episode?.published
			? { label: dt.publishedDate, local: toLocalInput(new Date(episode.published)) }
			: null
	);

	function openPlays(row: PodcastEpisode) {
		selected = row.id;
		playsOpen = true;
	}

	function sub(row: PodcastEpisode): string {
		return [
			row.published ? new Date(row.published).toLocaleDateString(undefined, { dateStyle: 'medium' }) : '',
			row.duration,
			row.play_count ? dt.playsCount(row.play_count) : ''
		]
			.filter(Boolean)
			.join(' · ');
	}
</script>

<svelte:head>
	<title>{screen.show.title} · Floppy</title>
</svelte:head>

<main class="ct-detail">
	<div class="mx-auto max-w-[1400px] px-5 md:px-8">
		<MediaHero
			title={screen.show.title}
			image={screen.show.image}
			kind="Podcast"
			backType="podcast"
			meta={screen.show.author ? [screen.show.author] : []}
			activity={screen.activity}
			status={screen.tracker?.status}
			track={{ mediaType: 'podcast', source: screen.show.source, mediaId: screen.show.uuid }}
			links={screen.links}
		>
			{#if screen.show.description}
				<p class={['ct-media-bio', longDescription && !descriptionOpen && 'is-clamped']}>
					{screen.show.description}
				</p>
				{#if longDescription}
					<button type="button" class="ct-detail-more" onclick={() => (descriptionOpen = !descriptionOpen)}>
						{descriptionOpen ? dt.showLess : dt.readMore}
					</button>
				{/if}
			{/if}
		</MediaHero>

		<div class="ct-detail-sections">
			<section aria-labelledby="ct-episodes-title">
				<div class="ct-row-head"><h2 class="ct-row-title" id="ct-episodes-title">{dt.episodes}</h2></div>
				{#if episodes.length}
					<ol class="ct-media-rows ct-episode-list" aria-busy={extra.loading}>
						{#each episodes as row (row.id)}
							<li>
								<button
									type="button"
									class="ct-media-row"
									aria-label={dt.openPlays(row.title)}
									onclick={() => openPlays(row)}
								>
									<span class="ct-media-row__body">
										<span class="ct-media-row__title">{row.title}</span>
										{#if sub(row)}
											<span class={['ct-media-row__sub', row.play_count && 'is-played']}>{sub(row)}</span>
										{/if}
									</span>
								</button>
							</li>
						{/each}
					</ol>
					{#if extra.next}
						<div class="ct-ep-more">
							<button type="button" class="ct-row-link" onclick={showMore} disabled={extra.loading}>
								{dt.episodesMore}
							</button>
						</div>
					{/if}
					{#if extra.failed}
						<p class="px-4 py-6 text-center text-muted" role="alert">{dt.episodesFailed}</p>
					{/if}
				{:else}
					<p class="ct-detail-note">{dt.noEpisodes}</p>
				{/if}
			</section>

			{#if screen.details.length || screen.show.website_url}
				<section aria-labelledby="ct-details-title">
					<div class="ct-row-head"><h2 class="ct-row-title" id="ct-details-title">{dt.details}</h2></div>
					<dl class="ct-info-grid">
						{#each screen.details as row (row.label)}
							<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
						{/each}
						{#if screen.show.website_url}
							<div>
								<dt>{dt.website}</dt>
								<dd class="ct-info-links">
									<a href={screen.show.website_url} target="_blank" rel="noopener noreferrer">
										{screen.show.website_url.replace(/^https?:\/\//, '').replace(/\/$/, '')}
									</a>
								</dd>
							</div>
						{/if}
					</dl>
				</section>
			{/if}

			{#if screen.genres.length}
				<section aria-labelledby="ct-genres-title">
					<div class="ct-row-head"><h2 class="ct-row-title" id="ct-genres-title">{dt.genres}</h2></div>
					<div class="ct-chip-list">
						{#each screen.genres as genre (genre.name)}
							{#if genre.url}
								<a class="ct-genre-chip" {...genreLink(genre.url)}>{genre.name}</a>
							{:else}
								<span class="ct-genre-chip">{genre.name}</span>
							{/if}
						{/each}
					</div>
				</section>
			{/if}
		</div>
	</div>
</main>

{#if episode}
	{#await import('#lib/details/PlaysDialog.svelte') then view}
		<view.default
			bind:open={playsOpen}
			title={episode.title}
			kind="podcast"
			plays={episode.plays}
			{suggestion}
			body={{ show_id: screen.show.id, episode_id: episode.id }}
			onchange={() => invalidateAll()}
		/>
	{/await}
{/if}
