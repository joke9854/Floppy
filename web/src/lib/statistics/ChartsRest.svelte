<script lang="ts">
	import { combinedBars, consumptionTiles, ratingBars, SLUG_LABEL, statusSlices } from './charts.ts';
	import Donut from './Donut.svelte';
	import StackedBars from './StackedBars.svelte';
	import './charts.css';
	import { cs } from './chart-strings.ts';
	import { st } from './strings.ts';
	import type { StatisticsScreen } from './types.ts';

	/**
	 * H2, below Activity History: Hours by Month, Day of Week and Time of
	 * Day, the consumption tiles, Status Composition, Rating Distribution,
	 * Status Breakdown and Average Rating, each for the picked type.
	 */
	let { screen, mediaType }: { screen: StatisticsScreen; mediaType: string } = $props();

	const charts = $derived(screen.charts);
	const combined = $derived([
		{ title: cs.byMonth, bars: combinedBars(charts.combined.by_month, mediaType) },
		{ title: cs.byWeekday, bars: combinedBars(charts.combined.by_weekday, mediaType) },
		{ title: cs.byTime, bars: combinedBars(charts.combined.by_time_of_day, mediaType) }
	]);
	const tiles = $derived(consumptionTiles(charts.consumption[mediaType]));
	const slices = $derived(statusSlices(charts.status, mediaType));
	const statusTotal = $derived(slices.reduce((sum, slice) => sum + slice.value, 0));
	const ratings = $derived(ratingBars(charts.ratings, mediaType));
	const typeLabel = $derived(SLUG_LABEL[mediaType] ?? '');
	const rows = $derived(
		charts.status.labels
			.map((label, index) => ({
				label,
				values: charts.status.series.map((series) => series.values[index] || 0)
			}))
			.filter((row) => (mediaType === 'all' || row.label === typeLabel) && row.values.some((value) => value > 0))
	);
	const average = $derived(
		screen.media_types
			.filter((option) => option.value !== 'all' && (mediaType === 'all' || option.value === mediaType))
			.map((option) => {
				const summary = screen.summaries[option.value];
				const color = charts.ratings.series.find((series) => series.label === SLUG_LABEL[option.value])?.color;
				return { label: option.label, score: summary?.has_score ? Number(summary.average_score) : null, color: color || '#9ca3af' };
			})
			.filter((row): row is { label: string; score: number; color: string } => row.score !== null && !Number.isNaN(row.score))
			.sort((a, b) => b.score - a.score)
	);
	const count = (value: number) => value.toLocaleString('en-US');
</script>

<div class="ct-stats-grid3">
	{#each combined as chart (chart.title)}
		<section class="ct-stats-card">
			<h2 class="ct-stats-card__title is-spaced">{chart.title}</h2>
			{#if chart.bars}
				<StackedBars bars={chart.bars} unit={st.hours.toLowerCase()} label={chart.title} width={360} />
			{:else}
				<p class="ct-stats-none">{cs.noFilterData}</p>
			{/if}
		</section>
	{/each}
</div>

{#if tiles.length}
	<div class="ct-stats-tiles">
		{#each tiles as tile, index (index)}
			<div class={['ct-stat-card', tile.bonus && 'is-bonus']}>
				<div>
					<h3>{tile.label}</h3>
					<p class="ct-stat-card__value">{tile.value}</p>
					{#if tile.caption}<p class="ct-stat-card__sub">{tile.caption}</p>{/if}
				</div>
			</div>
		{/each}
	</div>
{/if}

<div class="ct-stats-grid2">
	<section class="ct-stats-card">
		<h2 class="ct-stats-card__title">{cs.statusComposition}</h2>
		<p class="ct-stats-card__sub is-spaced">
			{mediaType === 'all' ? cs.statusCompositionSub : cs.statusOf(typeLabel)}
		</p>
		{#if slices.length}
			<Donut {slices} total={count(statusTotal)} caption={cs.totalItems} format={count} label={cs.statusComposition} />
		{:else}
			<p class="ct-stats-none">{cs.noStatus}</p>
		{/if}
	</section>
	<section class="ct-stats-card">
		<h2 class="ct-stats-card__title">{cs.ratingDistribution}</h2>
		<p class="ct-stats-card__sub is-spaced">{cs.ratingDistributionSub}</p>
		{#if ratings.total}
			<StackedBars bars={ratings.bars} unit={cs.items} label={cs.ratingDistribution} width={480} />
		{:else}
			<p class="ct-stats-none">{mediaType === 'all' ? cs.noRatings : cs.noRatingsFilter}</p>
		{/if}
	</section>
</div>

<div class="ct-stats-grid3 is-wide-first">
	<section class="ct-stats-card">
		<h2 class="ct-stats-card__title">{cs.statusBreakdown}</h2>
		<p class="ct-stats-card__sub is-spaced">{mediaType === 'all' ? cs.statusBreakdownSub : cs.statusCounts(typeLabel)}</p>
		{#if rows.length}
			<div class="ct-stats-table-scroll">
				<table class="ct-stats-table">
					<thead>
						<tr>
							<th></th>
							{#each charts.status.series as series, index (index)}<th>{series.label}</th>{/each}
							<th>{cs.totalColumn}</th>
						</tr>
					</thead>
					<tbody>
						{#each rows as row (row.label)}
							<tr>
								<th scope="row">{row.label}</th>
								{#each row.values as value, index (index)}
									<td class={value ? '' : 'is-zero'}>{count(value)}</td>
								{/each}
								<td class="is-total">{count(row.values.reduce((a, b) => a + b, 0))}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else}
			<p class="ct-stats-none">{cs.noStatus}</p>
		{/if}
	</section>
	<section class="ct-stats-card">
		<h2 class="ct-stats-card__title">{st.averageRating}</h2>
		<p class="ct-stats-card__sub is-spaced">{cs.averageRatingSub}</p>
		{#if average.length}
			<ul class="ct-stats-avg">
				{#each average as row (row.label)}
					<li>
						<span class="ct-stats-avg__label">{row.label}</span>
						<span class="ct-stats-avg__bar">
							<i style:width="{Math.max(0, Math.min(100, (row.score / screen.rating_scale_max) * 100))}%" style:background={row.color}></i>
						</span>
						<span class="ct-stats-avg__score">{row.score.toFixed(1)}</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="ct-stats-none">{cs.noRatings}</p>
		{/if}
	</section>
</div>
