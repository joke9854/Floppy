import type { components } from '#lib/api/client.ts';

export type StatisticsScreen = components['schemas']['StatisticsScreen'];
export type PlayedHours = components['schemas']['StatisticsScreenPlayedHours'];

/** The page's query the screen API reads; `media-type` stays in the browser. */
export const SCREEN_KEYS = ['start-date', 'end-date', 'compare'] as const;

/** The API query for this page URL: only the range and compare, as the page reloads for them. */
export function screenQuery(params: Pick<URLSearchParams, 'get'>): string {
	const query = new URLSearchParams();
	for (const key of SCREEN_KEYS) {
		const value = params.get(key);
		if (value) query.set(key, value);
	}
	const text = query.toString();
	return text ? `?${text}` : '';
}

/** The page URL's query with these changes (`null` removes a key). */
export function withQuery(params: { toString(): string }, changes: Record<string, string | null>): string {
	const next = new URLSearchParams(params.toString());
	for (const [key, value] of Object.entries(changes)) {
		if (value === null || value === '') next.delete(key);
		else next.set(key, value);
	}
	const text = next.toString();
	return text ? `?${text}` : '';
}

export type Bucket = 'day' | 'week' | 'month' | 'year';

/** A local date from YYYY-MM-DD (no time zone shift), as the page parses it. */
function localDate(iso: string): Date {
	const [year, month, day] = iso.split('-').map(Number);
	return new Date(year, (month || 1) - 1, day || 1);
}

const pad = (value: number) => String(value).padStart(2, '0');
const isoDay = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/**
 * The bar size for Played Hours by Media Type (statistics-charts.js
 * chooseBucket): days up to 45 days of data or a month's span, then weeks,
 * months, years, keeping at most 36 bars.
 */
export function chooseBucket(days: string[], firstDay = '', lastDay = ''): Bucket {
	if (days.length && days.length <= 45) return 'day';
	const start = firstDay || days[0];
	const end = lastDay || days[days.length - 1];
	if (!start || !end) return 'month';
	const from = localDate(start);
	const to = localDate(end);
	const spanDays = Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
	if (spanDays <= 31) return 'day';
	if (Math.ceil(spanDays / 7) <= 36) return 'week';
	const spanMonths = (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth()) + 1;
	return spanMonths <= 36 ? 'month' : 'year';
}

function bucketKey(bucket: Bucket, day: string): string {
	if (bucket === 'day') return day;
	const date = localDate(day);
	if (bucket === 'week') {
		// Weeks start on Monday, as the page's getWeekStartIso.
		date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
		return isoDay(date);
	}
	if (bucket === 'month') return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
	return String(date.getFullYear());
}

/** A bar's label, as the page's formatBucketLabel (English, so server and browser agree). */
export function bucketLabel(bucket: Bucket, key: string, spansYears: boolean, nowYear: number): string {
	if (bucket === 'year') return key;
	if (bucket === 'month') {
		const date = localDate(`${key}-01`);
		return spansYears || date.getFullYear() !== nowYear
			? date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
			: date.toLocaleDateString('en-US', { month: 'long' });
	}
	const date = localDate(key);
	return date.toLocaleDateString('en-US', {
		month: 'short',
		day: 'numeric',
		...(spansYears || date.getFullYear() !== nowYear ? { year: 'numeric' } : {})
	});
}

export interface Bars {
	labels: string[];
	series: { label: string; media_type: string; color: string; values: number[] }[];
}

/** Played Hours by Media Type as bars: the days summed per bucket (aggregateDailyToBucket). */
export function hoursBars(played: PlayedHours, firstDay = '', lastDay = '', nowYear = new Date().getFullYear()): Bars {
	const bucket = chooseBucket(played.days, firstDay, lastDay);
	const keys: string[] = [];
	const index = new Map<string, number>();
	const sums = played.series.map(() => [] as number[]);
	played.days.forEach((day, position) => {
		const key = bucketKey(bucket, day);
		let slot = index.get(key);
		if (slot === undefined) {
			slot = keys.length;
			index.set(key, slot);
			keys.push(key);
			sums.forEach((values) => values.push(0));
		}
		played.series.forEach((series, which) => {
			sums[which][slot] = +(sums[which][slot] + (Number(series.values[position]) || 0)).toFixed(4);
		});
	});
	const order = keys.map((key, slot) => ({ key, slot })).sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
	const first = firstDay || played.days[0] || '';
	const last = lastDay || played.days[played.days.length - 1] || '';
	const spansYears = Boolean(first && last && first.slice(0, 4) !== last.slice(0, 4));
	return {
		labels: order.map(({ key }) => bucketLabel(bucket, key, spansYears, nowYear)),
		series: played.series.map((series, which) => ({
			label: series.label,
			media_type: series.media_type,
			color: series.color,
			values: order.map(({ slot }) => sums[which][slot])
		}))
	};
}

/** The hero's "{n} {titles}" noun and its flavour, per type (date-range.js). */
export const TYPE_NOUN: Record<string, string> = {
	all: 'titles',
	movie: 'films',
	tv: 'shows',
	game: 'games',
	book: 'books',
	anime: 'titles',
	music: 'albums',
	podcast: 'podcasts',
	comic: 'comics',
	manga: 'manga'
};

export const TYPE_FLAVOUR: Record<string, string> = {
	all: 'stories, ideas, and worlds',
	movie: 'film and storytelling',
	tv: 'episodes and seasons',
	game: 'play and adventure',
	book: 'reading and discovery',
	anime: 'anime and storytelling',
	music: 'music and discovery',
	podcast: 'listening and learning',
	comic: 'comics and art',
	manga: 'manga and art'
};

/** Whether a cache-status answer says a statistics rebuild is still running. */
export function rebuilding(status: { is_refreshing?: boolean; refresh_scheduled?: boolean }): boolean {
	return Boolean(status.is_refreshing || status.refresh_scheduled);
}
