<script lang="ts">
	import { GENRE_PALETTE, GENRE_TYPES, hoursLabel, SLUG_LABEL } from './charts.ts';
	import Donut from './Donut.svelte';
	import Rhythm from './Rhythm.svelte';
	import './charts.css';
	import { cs } from './chart-strings.ts';
	import type { StatisticsScreen } from './types.ts';

	/**
	 * H2, above Activity History: Activity Rhythm and Hours by Media Type,
	 * which becomes Top Genres for a type that has genres (statistics.html).
	 */
	let { screen, mediaType }: { screen: StatisticsScreen; mediaType: string } = $props();

	const charts = $derived(screen.charts);
	const matrix = $derived(charts.rhythm[mediaType] ?? (mediaType !== 'all' ? charts.rhythm.all : undefined));
	const genres = $derived(GENRE_TYPES.has(mediaType) ? (charts.top_genres[mediaType] ?? []) : []);
	const byGenre = $derived(mediaType !== 'all' && genres.length > 0);
	const slices = $derived(
		byGenre
			? genres.map((genre, index) => ({ label: genre.name, value: genre.hours, color: GENRE_PALETTE[index % GENRE_PALETTE.length] }))
			: charts.hours_by_type.labels.map((label, index) => ({
					label,
					value: charts.hours_by_type.values[index] ?? 0,
					color: charts.hours_by_type.colors[index] ?? '#6366f1'
				}))
	);
	// The centre shows actual time: genres overlap, so their sum can be larger.
	const totalHours = $derived(
		byGenre ? (screen.summaries[mediaType]?.total_hours ?? 0) : slices.reduce((sum, slice) => sum + slice.value, 0)
	);
	const typeName = $derived((SLUG_LABEL[mediaType] ?? '').toLowerCase());
</script>

<div class="ct-stats-grid2">
	<section class="ct-stats-card">
		<div class="ct-stats-card__head">
			<div>
				<h2 class="ct-stats-card__title">{cs.rhythm}</h2>
				<p class="ct-stats-card__sub">{cs.rhythmSub}</p>
			</div>
		</div>
		{#if matrix}
			<Rhythm {matrix} />
		{:else}
			<p class="ct-stats-none">{cs.noRhythm}</p>
		{/if}
	</section>
	<section class="ct-stats-card">
		<div class="ct-stats-card__head">
			<div>
				<h2 class="ct-stats-card__title">{byGenre ? cs.topGenres : cs.hoursByType}</h2>
				<p class="ct-stats-card__sub">{byGenre ? cs.genresSub(typeName) : cs.hoursByTypeSub}</p>
			</div>
			{#if byGenre}
				<span class="ct-stats-info" title={cs.genresOverlap}>i</span>
			{/if}
		</div>
		{#if slices.some((slice) => slice.value > 0)}
			<Donut
				{slices}
				total={hoursLabel(totalHours)}
				caption={cs.total}
				format={hoursLabel}
				label={byGenre ? cs.topGenres : cs.hoursByType}
			/>
		{:else}
			<p class="ct-stats-none">{cs.noFilterData}</p>
		{/if}
	</section>
</div>
