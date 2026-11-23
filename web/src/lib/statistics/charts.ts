import type { components } from '#lib/api/client.ts';
import type { Bars } from './types.ts';

type Chart = components['schemas']['StatisticsScreenChart'];
type Consumption = components['schemas']['StatisticsScreenConsumption'];

/** The page's slug-to-label map (statistics-charts.js MEDIA_SLUG_TO_LABEL). */
export const SLUG_LABEL: Record<string, string> = {
	tv: 'TV Show',
	movie: 'Movie',
	anime: 'Anime',
	music: 'Music',
	podcast: 'Podcast',
	book: 'Book',
	comic: 'Comic',
	boardgame: 'Board Game',
	game: 'Game',
	manga: 'Manga'
};

/** Top Genres colours, in order (GENRE_PALETTE). */
export const GENRE_PALETTE = [
	'#6366f1',
	'#ec4899',
	'#10b981',
	'#f59e0b',
	'#3b82f6',
	'#8b5cf6',
	'#ef4444',
	'#14b8a6',
	'#f97316',
	'#a855f7',
	'#06b6d4',
	'#84cc16'
];

export const GENRE_TYPES = new Set(['tv', 'movie', 'anime', 'music', 'game']);

/** Activity Rhythm's six tiers by quantile of the non-zero cells (drawRhythmChart). */
export function rhythmTiers(matrix: number[][], tiers = 6): number[][] {
	const values = matrix
		.flat()
		.filter((value) => value > 0)
		.sort((a, b) => a - b);
	const tierFor = (value: number) => {
		if (value <= 0 || !values.length) return 0;
		let low = 0;
		let high = values.length;
		while (low < high) {
			const middle = (low + high) >> 1;
			if (values[middle] < value) low = middle + 1;
			else high = middle;
		}
		return Math.min(tiers, Math.floor((low / values.length) * tiers) + 1);
	};
	return matrix.map((row) => row.map(tierFor));
}

export interface Slice {
	label: string;
	value: number;
	color: string;
}

/**
 * Status Composition: every type's count per status, or the picked type's
 * column (empty statuses dropped), as the page draws it.
 */
export function statusSlices(status: Chart, mediaType: string): Slice[] {
	if (mediaType === 'all') {
		return status.series
			.map((series) => ({ label: series.label, value: series.values.reduce((a, b) => a + b, 0), color: series.color }))
			.filter((slice) => slice.value > 0);
	}
	const column = status.labels.indexOf(SLUG_LABEL[mediaType] ?? '');
	if (column < 0) return [];
	return status.series
		.map((series) => ({ label: series.label, value: series.values[column] || 0, color: series.color }))
		.filter((slice) => slice.value > 0);
}

/** Rating Distribution: items per score, every type or the picked one. */
export function ratingBars(ratings: Chart, mediaType: string): { bars: Bars; total: number } {
	const series =
		mediaType === 'all' ? ratings.series : ratings.series.filter((entry) => entry.label === SLUG_LABEL[mediaType]);
	const values = ratings.labels.map((_, index) => series.reduce((sum, entry) => sum + (entry.values[index] || 0), 0));
	return {
		bars: { labels: ratings.labels, series: [{ label: 'Items', media_type: '', color: '#6366f1', values }] },
		total: values.reduce((a, b) => a + b, 0)
	};
}

/** A combined hours chart for the type (the page falls back to nothing). */
export function combinedBars(charts: Record<string, Chart>, mediaType: string): Bars | null {
	const chart = charts[mediaType];
	if (!chart || !chart.labels.length || !chart.series.some((entry) => entry.values.some((value) => value > 0))) return null;
	return chart;
}

export interface Tile {
	label: string;
	value: string;
	caption: string;
	bonus: boolean;
}

const fmt = (value: number, decimals: number) =>
	value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

/** The consumption tiles (date-range.js consumptionTiles). */
export function consumptionTiles(consumption: Consumption | undefined): Tile[] {
	if (!consumption?.has_data || !consumption.primary) return [];
	const { primary, secondary } = consumption;
	const unit = primary.unit === 'Hours' ? 'hrs' : primary.unit;
	const buckets = [
		['Per Year', 'per_year'],
		['Per Month', 'per_month'],
		['Per Day', 'per_day']
	] as const;
	const tiles: Tile[] = buckets.map(([label, field]) => ({
		label,
		value: `${fmt(primary[field], 1)} ${unit}`,
		caption: secondary ? `${fmt(secondary[field], 1)} ${secondary.unit}` : '',
		bonus: false
	}));
	for (const bonus of consumption.bonuses) {
		if (bonus.kind === 'playtime') {
			tiles.push({
				label: 'Average Playtime',
				value: bonus.value < 1 ? `${Math.round(bonus.value * 60)} min` : `${fmt(bonus.value, 1)} hrs`,
				caption: 'Per Day',
				bonus: true
			});
		} else if (bonus.kind === 'length') {
			tiles.push({ label: 'Average Length', value: fmt(bonus.value, 0), caption: 'Pages', bonus: true });
		} else {
			tiles.push({ label: bonus.label, value: `${fmt(bonus.value, 2)} ${bonus.unit}`, caption: '', bonus: true });
		}
	}
	return tiles;
}

/** Hours as the page's centre total: "12.3h" (one decimal under 100). */
export function hoursLabel(hours: number): string {
	return `${hours >= 100 ? Math.round(hours).toLocaleString('en-US') : fmt(hours, 1)}h`;
}
