<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Info from '@lucide/svelte/icons/info';
	import Play from '@lucide/svelte/icons/play';
	import StatusChip from '#lib/home/StatusChip.svelte';
	import { fadeIn } from '#lib/media/fade.ts';
	import { t } from '#lib/strings.ts';
	import { dt } from '#lib/details/strings.ts';
	import {
		detailApiPath,
		type DetailCard,
		type DetailEpisode,
		type DetailIssue,
		type DetailSeason,
		type DetailSections,
		type DetailTrailer
	} from './api.ts';
	import EpisodeRow from './EpisodeRow.svelte';
	import IssueRow from './IssueRow.svelte';
	import { detailLink, genreLink } from './link.ts';
	import PeopleRail from './PeopleRail.svelte';

	/**
	 * The detail page below the hero (ct/detail_secondary.html), loaded with
	 * the sections it shows so the page's first load is the hero alone. The
	 * page keeps the state (the season on screen, the trailer playing); this
	 * draws it and reports clicks.
	 */
	let {
		sections,
		mediaType,
		source,
		mediaId,
		current,
		trailers,
		trackTime,
		onpick,
		onmore,
		onsaved,
		oninfo,
		onplay
	}: {
		sections: DetailSections;
		mediaType: string;
		source: string;
		mediaId: string;
		current: { season: DetailSeason | null; selected: number | null; loading: boolean; failed: boolean };
		trailers: DetailTrailer[];
		trackTime: boolean;
		onpick: (season: number) => void;
		onmore: () => void;
		onsaved: () => void;
		oninfo: (season: number) => void;
		onplay: (key: string) => void;
	} = $props();

	// The page's section order; Trailers has no layout key and sits after Cast.
	// Books, manga, games, comics and board games add Time to Beat, Genres and Studios (P4-L1).
	const ORDER = [
		'episodes',
		'history',
		'related',
		'cast',
		'trailers',
		'recommendations',
		'game_lengths',
		'details',
		'genres',
		'studios'
	];
	const sectionOrder = $derived(
		ORDER.filter((key) => key === 'trailers' || sections.sections.includes(key))
	);

	// A comic volume's issues: the sections' own page, then the pages "Show ..." loads.
	let loadedIssues = $state.raw<{
		for: DetailSections;
		extra: DetailIssue[];
		more: DetailSections['issues_more'];
		loading: boolean;
		failed: boolean;
	} | null>(null);
	const issueState = $derived(
		loadedIssues && loadedIssues.for === sections
			? loadedIssues
			: {
					for: sections,
					extra: [] as DetailIssue[],
					more: sections.issues_more,
					loading: false,
					failed: false
				}
	);

	// A flat MAL anime's mapped episodes: the sections' own page, then "Show ..." pages.
	let loadedFlat = $state.raw<{
		for: DetailSections;
		extra: DetailEpisode[];
		more: DetailSections['flat_more'];
		loading: boolean;
		failed: boolean;
	} | null>(null);
	const flatState = $derived(
		loadedFlat && loadedFlat.for === sections
			? loadedFlat
			: {
					for: sections,
					extra: [] as DetailEpisode[],
					more: sections.flat_more,
					loading: false,
					failed: false
				}
	);

	async function moreFlat() {
		const more = flatState.more;
		if (!more || flatState.loading) return;
		const forSections = sections;
		loadedFlat = { ...flatState, loading: true, failed: false };
		try {
			const response = await fetch(
				detailApiPath(mediaType, source, mediaId, 'sections', null, more.page),
				{ credentials: 'same-origin' }
			);
			if (!response.ok) throw new Error(String(response.status));
			const next = (await response.json()) as DetailSections;
			if (forSections !== sections) return;
			loadedFlat = {
				for: forSections,
				extra: [...flatState.extra, ...next.flat_episodes],
				more: next.flat_more,
				loading: false,
				failed: false
			};
		} catch {
			if (forSections === sections) loadedFlat = { ...flatState, loading: false, failed: true };
		}
	}

	async function moreIssues() {
		const more = issueState.more;
		if (!more || issueState.loading) return;
		const forSections = sections;
		loadedIssues = { ...issueState, loading: true, failed: false };
		try {
			const response = await fetch(
				detailApiPath(mediaType, source, mediaId, 'sections', null, more.page),
				{ credentials: 'same-origin' }
			);
			if (!response.ok) throw new Error(String(response.status));
			const next = (await response.json()) as DetailSections;
			if (forSections !== sections) return;
			loadedIssues = {
				for: forSections,
				extra: [...issueState.extra, ...next.issues],
				more: next.issues_more,
				loading: false,
				failed: false
			};
		} catch {
			if (forSections === sections) loadedIssues = { ...issueState, loading: false, failed: true };
		}
	}
</script>

	<div class="ct-detail-sections">
		{#each sectionOrder as key (key)}
			{#if key === 'episodes' && sections.seasons.length}
				<section aria-labelledby="ct-episodes-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-episodes-title">{dt.episodes}</h2>
					</div>
					{#if sections.seasons.length > 1}
						<div class="ct-season-picker" role="tablist" aria-label={dt.seasons}>
							{#each sections.seasons as cover (cover.number)}
								<div class="ct-season-item">
									<button
									type="button"
									class="ct-season-cover"
									role="tab"
									aria-selected={cover.number === current.selected}
									onclick={() => onpick(cover.number)}
								>
									<span class="ct-season-cover__art">
										{#if cover.image}
											<img
												alt=""
												class="ct-fade-img"
												src={cover.image}
												width="185"
												height="278"
												loading="lazy"
												decoding="async"
												use:fadeIn
											/>
										{/if}
									</span>
									<span class="ct-season-cover__label">{cover.label}</span>
									<span class="ct-season-cover__short">{cover.short}</span>
								</button>
									<button
										type="button"
										class="ct-season-info-btn"
										title={dt.aboutSeason(cover.label)}
										aria-label={dt.aboutSeason(cover.label)}
										onclick={() => oninfo(cover.number)}
									>
										<Info class="size-4" aria-hidden="true" />
									</button>
								</div>
							{/each}
						</div>
					{/if}
					<div class={['ct-episode-list', current.loading && 'is-loading']} aria-busy={current.loading}>
						{#if current.season}
							{#if current.season.progress}
								{@const progress = current.season.progress}
								<div class="ct-season-progress">
									<p class="ct-season-progress__count">
										{dt.episodesWatched(progress.watched, progress.total)}
										<span>{progress.percent}%</span>
									</p>
									{#if progress.dashes.length}
										<ol class="ct-season-dashes" aria-hidden="true">
											{#each progress.dashes as dash, index (index)}
												<li
													class={['ct-season-dash', dash.percent >= 100 && 'is-done']}
													title="{dash.label} · {dash.percent}%"
												>
													<span style:width="{dash.percent}%"></span>
												</li>
											{/each}
										</ol>
									{/if}
								</div>
							{/if}
							{#each current.season.episodes as episode (episode.episode_number)}
								<EpisodeRow {episode} {trackTime} {onsaved} />
							{/each}
							{#if current.season.load_more}
								<div class="ct-ep-more">
									<button type="button" class="ct-row-link" onclick={onmore} disabled={current.loading}>
										{current.season.load_more.label}
									</button>
								</div>
							{/if}
						{:else if !current.failed}
							<div class="ct-ep-skeleton"></div>
							<div class="ct-ep-skeleton"></div>
							<div class="ct-ep-skeleton"></div>
						{/if}
						{#if current.failed}
							<p class="px-4 py-6 text-center text-muted" role="alert">{dt.seasonFailed}</p>
						{/if}
					</div>
				</section>
			{:else if key === 'episodes' && sections.issues.length}
				<section aria-labelledby="ct-issues-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-issues-title">{dt.issues}</h2>
					</div>
					<div class={['ct-episode-list', issueState.loading && 'is-loading']} aria-busy={issueState.loading}>
						{#each [...sections.issues, ...issueState.extra] as issue (issue.media_id)}
							<IssueRow {issue} />
						{/each}
						{#if issueState.more}
							<div class="ct-ep-more">
								<button type="button" class="ct-row-link" onclick={moreIssues} disabled={issueState.loading}>
									{dt.showMore(issueState.more.label)}
								</button>
							</div>
						{/if}
						{#if issueState.failed}
							<p class="px-4 py-6 text-center text-muted" role="alert">{dt.issuesFailed}</p>
						{/if}
					</div>
				</section>
			{:else if key === 'episodes' && sections.flat_episodes.length}
				<section aria-labelledby="ct-flat-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-flat-title">{dt.episodes}</h2>
					</div>
					{#if sections.flat_note}<p class="px-4 pb-2 text-muted">{sections.flat_note}</p>{/if}
					<div class={['ct-episode-list', flatState.loading && 'is-loading']} aria-busy={flatState.loading}>
						{#each [...sections.flat_episodes, ...flatState.extra] as episode, index (index)}
							<EpisodeRow {episode} {trackTime} />
						{/each}
						{#if flatState.more}
							<div class="ct-ep-more">
								<button type="button" class="ct-row-link" onclick={moreFlat} disabled={flatState.loading}>
									{dt.showMore(flatState.more.label)}
								</button>
							</div>
						{/if}
						{#if flatState.failed}
							<p class="px-4 py-6 text-center text-muted" role="alert">{dt.episodesFailed}</p>
						{/if}
					</div>
				</section>
			{:else if key === 'game_lengths' && sections.game_lengths}
				{@const lengths = sections.game_lengths}
				<section aria-labelledby="ct-lengths-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-lengths-title">{dt.timeToBeat}</h2>
						{#if lengths.source_label}
							{#if lengths.source_url}
								<a
									class="ct-source-pill"
									href={lengths.source_url}
									target="_blank"
									rel="noreferrer noopener">{lengths.source_label}</a
								>
							{:else}
								<span class="ct-source-pill">{lengths.source_label}</span>
							{/if}
						{/if}
					</div>
					{#if lengths.available}
						<ul class="ct-lengths">
							{#each lengths.cards as card (card.label)}
								<li class="ct-length">
									<span class="ct-length__label">{card.label}</span>
									<span class="ct-length__value">{card.value}</span>
									<span class="ct-length__count">{dt.submissions(card.count)}</span>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="ct-detail-note">
							{lengths.pending ? dt.timeToBeatPending : dt.timeToBeatNone}
						</p>
					{/if}
				</section>
			{:else if key === 'history' && sections.plays.length}
				<section aria-labelledby="ct-plays-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-plays-title">{dt.yourPlays}</h2>
						<a class="ct-row-link" {...detailLink(sections.history_url)}
							>{t.history} <ChevronRight class="size-4" aria-hidden="true" /></a
						>
					</div>
					<ul class="ct-plays">
						{#each sections.plays as play, index (index)}
							<li class="ct-play">
								<span class={['ct-play__icon', play.status === 'Completed' && 'is-done']} aria-hidden="true">
									{#if play.status === 'Completed'}
										<Check class="size-4" />
									{:else}
										<ChevronRight class="size-4" />
									{/if}
								</span>
								<span class="ct-play__text">
									<span class="ct-play__title">{play.label}</span>
									<span class="ct-play__sub"
										>{play.when}{play.score !== null ? ` · ${dt.rated(play.score)}` : ''}</span
									>
								</span>
							</li>
						{/each}
					</ul>
				</section>
			{:else if key === 'related'}
				{#each sections.related as list (list.name)}
					<section aria-label={list.name}>
						<div class="ct-row-head"><h2 class="ct-row-title">{list.name}</h2></div>
						<div class="ct-detail-rail">
							{#each list.cards as card (card.url)}
								{@render poster(card)}
							{/each}
						</div>
					</section>
				{/each}
			{:else if key === 'cast' && (sections.cast.length || sections.crew.length)}
				<PeopleRail
					cast={sections.cast}
					crew={sections.crew}
					viewAllUrl={sections.cast_view_all_url}
				/>
			{:else if key === 'trailers' && trailers.length}
				<section aria-labelledby="ct-trailers-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-trailers-title">{dt.trailers}</h2>
					</div>
					<div class="ct-detail-rail">
						{#each trailers as trailer (trailer.key)}
							<button type="button" class="ct-trailer-card" onclick={() => onplay(trailer.key)}>
								<span class="ct-trailer-card__still">
									<img
										alt=""
										class="ct-fade-img"
										src={`https://img.youtube.com/vi/${encodeURIComponent(trailer.key)}/mqdefault.jpg`}
										width="320"
										height="180"
										loading="lazy"
										decoding="async"
										use:fadeIn
									/>
									<span class="ct-trailer-card__play" aria-hidden="true"><Play class="size-5" /></span>
								</span>
								<span class="ct-trailer-card__title">{trailer.name}</span>
								<span class="ct-trailer-card__sub"
									>{trailer.season ? `${dt.seasonNumber(trailer.season)} · ` : ''}{trailer.type}</span
								>
							</button>
						{/each}
					</div>
				</section>
			{:else if key === 'recommendations' && sections.recommendations.length}
				<section aria-labelledby="ct-more-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-more-title">{dt.moreLikeThis}</h2>
					</div>
					<div class="ct-detail-rail">
						{#each sections.recommendations as card (card.url)}
							{@render poster(card)}
						{/each}
					</div>
				</section>
			{:else if key === 'details' && (sections.info.length || sections.authors.length)}
				<section aria-labelledby="ct-info-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-info-title">{dt.information}</h2>
					</div>
					<dl class="ct-info-grid">
						{#each sections.info as row (row.label)}
							<div>
								<dt>{row.label}</dt>
								<dd>{row.value}</dd>
							</div>
						{/each}
						{#if sections.authors.length}
							<div>
								<dt>{sections.authors.length === 1 ? dt.author : dt.authors}</dt>
								<dd class="ct-info-links">
									{#each sections.authors as author, index (index)}
										{#if author.url}
											<a {...detailLink(author.url)}>{author.name}</a>
										{:else}
											<span>{author.name}</span>
										{/if}
									{/each}
								</dd>
							</div>
						{/if}
					</dl>
				</section>
			{:else if key === 'genres' && sections.genres.length}
				<section aria-labelledby="ct-genres-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-genres-title">{dt.genres}</h2>
					</div>
					<div class="ct-chip-list">
						{#each sections.genres as genre (genre.name)}
							{#if genre.url}
								<a class="ct-genre-chip" {...genreLink(genre.url)}>{genre.name}</a>
							{:else}
								<span class="ct-genre-chip">{genre.name}</span>
							{/if}
						{/each}
					</div>
				</section>
			{:else if key === 'studios' && sections.studios.length}
				<section aria-labelledby="ct-studios-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-studios-title">{dt.studios}</h2>
					</div>
					<ul class="ct-link-list">
						{#each sections.studios as studio, index (index)}
							<li>
								{#if studio.url}
									<a {...detailLink(studio.url)}>{studio.name}</a>
								{:else}
									{studio.name}
								{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}
		{/each}
	</div>

{#snippet poster(card: DetailCard)}
	<article class="ct-poster-card" data-media-type={card.media_type}>
		<a {...detailLink(card.url)} class="ct-poster-link">
			<span class="ct-poster-frame">
				<img
					alt={card.title}
					class="ct-poster-img ct-fade-img"
					src={card.poster}
					srcset={card.poster_srcset || undefined}
					sizes={card.poster_srcset ? '140px' : undefined}
					width="342"
					height="513"
					loading="lazy"
					decoding="async"
					use:fadeIn
				/>
			</span>
			<span class="ct-poster-title">{card.title}</span>
			<span class="ct-poster-sub">{card.subtitle}</span>
		</a>
		{#if card.status}
			<StatusChip status={card.status} />
		{/if}
	</article>
{/snippet}
