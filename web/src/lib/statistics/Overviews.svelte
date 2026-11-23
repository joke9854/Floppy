<script lang="ts">
	import './charts.css';
	import { detailLink } from '#lib/details/link.ts';
	import { cs } from './chart-strings.ts';
	import StackedBars from './StackedBars.svelte';
	import type { StatisticsScreen } from './types.ts';

	/**
	 * H3: each type's Activity Overview (the page's *_activity_overview and
	 * reading sections: charts by year, month or day, then ranked lists), the
	 * board games Most Played grid and the Top Played empty state.
	 */
	let { screen, mediaType }: { screen: StatisticsScreen; mediaType: string } = $props();

	const overviews = $derived(
		screen.overviews.filter((overview) => mediaType === 'all' || overview.media_type === mediaType)
	);
	const showBoardGames = $derived(screen.board_games.length > 0 && (mediaType === 'all' || mediaType === 'boardgame'));
	const linkFor = (href: string) => (href ? detailLink(href) : {});
</script>

{#each overviews as overview (overview.media_type)}
	<section class="ct-stats-overview" aria-labelledby="overview-{overview.media_type}">
		<header class="ct-stats-overview__head">
			<span class="ct-stats-overview__eyebrow">{overview.eyebrow}</span>
			<h2 id="overview-{overview.media_type}">{cs.activityOverview}</h2>
			<p>{screen.range.label}</p>
		</header>
		{#if overview.charts.length}
			<div class="ct-stats-grid3">
				{#each overview.charts as chart (chart.title)}
					<div class="ct-stats-card">
						<h3 class="ct-stats-card__title is-spaced">{chart.title}</h3>
						{#if chart.values.some((value) => value > 0)}
							<StackedBars
								bars={{ labels: chart.labels, series: [{ label: chart.title, media_type: overview.media_type, color: chart.color, values: chart.values }] }}
								unit=""
								label={chart.title}
								width={360}
							/>
						{:else}
							<p class="ct-stats-none">{chart.empty}</p>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
		<div class="ct-stats-lists">
			{#each overview.lists as list (list.title)}
				<div class="ct-stats-card">
					<h3 class="ct-stats-card__title is-spaced">{list.title}</h3>
					{#if list.items.length}
						<ol class="ct-stats-ranked">
							{#each list.items as entry, index (index)}
								<li>
									<span class="ct-stats-ranked__rank">{index + 1}</span>
									{#if entry.image}<img src={entry.image} alt="" loading="lazy" decoding="async" />{/if}
									<span class="ct-stats-ranked__text">
										{#if entry.href}
											<a {...linkFor(entry.href)}>{entry.title}</a>
										{:else}
											<span>{entry.title}</span>
										{/if}
										{#if entry.caption}<small>{entry.caption}</small>{/if}
									</span>
								</li>
							{/each}
						</ol>
					{:else}
						<p class="ct-stats-none">{list.empty}</p>
					{/if}
				</div>
			{/each}
		</div>
	</section>
{/each}

{#if showBoardGames}
	<section class="ct-stats-overview" aria-labelledby="overview-boardgame">
		<header class="ct-stats-overview__head is-row">
			<div>
				<span class="ct-stats-overview__eyebrow">{cs.boardGames}</span>
				<h2 id="overview-boardgame">{cs.mostPlayed}</h2>
			</div>
			<a href={screen.urls.board_games} data-sveltekit-reload>{cs.seeAllBoardGames}</a>
		</header>
		<div class="ct-stats-posters">
			{#each screen.board_games as entry, index (index)}
				<a {...linkFor(entry.href)} class="ct-stats-poster">
					{#if entry.image}
						<img src={entry.image} alt={entry.title} loading="lazy" decoding="async" />
					{:else}
						<span class="ct-stats-poster__blank" aria-hidden="true"></span>
					{/if}
					<span class="ct-stats-poster__title">{entry.title}</span>
					<span class="ct-stats-poster__sub">{entry.caption}</span>
				</a>
			{/each}
		</div>
	</section>
{/if}

{#if screen.no_top_played && mediaType === 'all'}
	<section class="ct-stats-card ct-stats-empty">
		<h3>{cs.noActivity}</h3>
		<p>{cs.noActivityBody}</p>
	</section>
{/if}
