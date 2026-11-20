<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Info from '@lucide/svelte/icons/info';
	import Play from '@lucide/svelte/icons/play';
	import StatusChip from '#lib/home/StatusChip.svelte';
	import { fadeIn } from '#lib/media/fade.ts';
	import { t } from '#lib/strings.ts';
	import type { DetailCard, DetailSeason, DetailSections, DetailTrailer } from './api.ts';
	import EpisodeRow from './EpisodeRow.svelte';
	import { detailLink } from './link.ts';
	import PeopleRail from './PeopleRail.svelte';

	/**
	 * The detail page below the hero (ct/detail_secondary.html), loaded with
	 * the sections it shows so the page's first load is the hero alone. The
	 * page keeps the state (the season on screen, the trailer playing); this
	 * draws it and reports clicks.
	 */
	let {
		sections,
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
	const ORDER = ['episodes', 'history', 'related', 'cast', 'trailers', 'recommendations', 'details'];
	const sectionOrder = $derived(
		ORDER.filter((key) => key === 'trailers' || sections.sections.includes(key))
	);
</script>

	<div class="ct-detail-sections">
		{#each sectionOrder as key (key)}
			{#if key === 'episodes' && sections.seasons.length}
				<section aria-labelledby="ct-episodes-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-episodes-title">{t.episodes}</h2>
					</div>
					{#if sections.seasons.length > 1}
						<div class="ct-season-picker" role="tablist" aria-label={t.seasons}>
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
										title={t.aboutSeason(cover.label)}
										aria-label={t.aboutSeason(cover.label)}
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
										{t.episodesWatched(progress.watched, progress.total)}
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
							<p class="px-4 py-6 text-center text-muted" role="alert">{t.seasonFailed}</p>
						{/if}
					</div>
				</section>
			{:else if key === 'history' && sections.plays.length}
				<section aria-labelledby="ct-plays-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-plays-title">{t.yourPlays}</h2>
						<a class="ct-row-link" href={sections.history_url} data-sveltekit-reload
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
										>{play.when}{play.score !== null ? ` · ${t.rated(play.score)}` : ''}</span
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
						<h2 class="ct-row-title" id="ct-trailers-title">{t.trailers}</h2>
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
									>{trailer.season ? `${t.seasonNumber(trailer.season)} · ` : ''}{trailer.type}</span
								>
							</button>
						{/each}
					</div>
				</section>
			{:else if key === 'recommendations' && sections.recommendations.length}
				<section aria-labelledby="ct-more-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-more-title">{t.moreLikeThis}</h2>
					</div>
					<div class="ct-detail-rail">
						{#each sections.recommendations as card (card.url)}
							{@render poster(card)}
						{/each}
					</div>
				</section>
			{:else if key === 'details' && sections.info.length}
				<section aria-labelledby="ct-info-title">
					<div class="ct-row-head">
						<h2 class="ct-row-title" id="ct-info-title">{t.information}</h2>
					</div>
					<dl class="ct-info-grid">
						{#each sections.info as row (row.label)}
							<div>
								<dt>{row.label}</dt>
								<dd>{row.value}</dd>
							</div>
						{/each}
					</dl>
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
