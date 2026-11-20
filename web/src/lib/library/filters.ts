import type { components } from '#lib/api/client.ts';

export type LibraryFilters = components['schemas']['LibraryFilters'];
export type LibraryFilterOptions = components['schemas']['LibraryFilterOptions'];

/** A URL change: a value, several values (repeated parameter), or null to remove it. */
export type ParamChanges = Record<string, string | string[] | null>;

/** The three-way choices, worded as the Django Library's menu. */
export const RATING_LABELS: Record<string, string> = {
	all: 'All',
	rated: 'Rated',
	not_rated: 'Not Rated'
};
export const COLLECTION_LABELS: Record<string, string> = {
	all: 'All',
	collected: 'Collected',
	not_collected: 'Not Collected'
};
export const PROGRESS_LABELS: Record<string, string> = {
	all: 'Any',
	not_caught_up: 'Not Caught Up',
	caught_up: 'Caught Up'
};
export const RELEASE_LABELS: Record<string, string> = {
	all: 'Any',
	released: 'Released',
	not_released: 'Not Released'
};

/** OR, AND, NOT: the order the Django menu cycles a multi-value mode. */
export function nextMode(mode: string): string {
	return mode === 'and' ? 'or' : mode === 'or' ? 'not' : 'and';
}

/** Every filter parameter "All" removes (sort, status and search stay). */
export const FILTER_PARAMS = [
	'rating',
	'collection',
	'progress',
	'genre',
	'implied_genre',
	'year',
	'completed_date_from',
	'completed_date_to',
	'completed_date_within',
	'completed_date_within_unit',
	'release',
	'source',
	'media_status',
	'language',
	'country',
	'platform',
	'platform_mode',
	'origin',
	'format',
	'author',
	'provider',
	'tag',
	'tag_mode'
] as const;

export function clearFilters(): ParamChanges {
	return Object.fromEntries(FILTER_PARAMS.map((key) => [key, null]));
}

const short = (value: string) => (value.length <= 3 ? value.toUpperCase() : value);

/** The "within the last N units" label of a relative completed date. */
export function withinLabel(amount: string, unit: string, units: { value: string; label: string }[]) {
	if (!amount) return '';
	const name = units.find((option) => option.value === unit)?.label ?? unit;
	return `Last ${amount} ${name.toLowerCase()}`;
}

/** The completed date filter as one label, or '' when it is off. */
export function completedLabel(filters: LibraryFilters, options: LibraryFilterOptions): string {
	const within = withinLabel(
		filters.completed_date_within,
		filters.completed_date_within_unit,
		options.relative_date_units
	);
	if (within) return within;
	const from = filters.completed_date_from;
	const to = filters.completed_date_to;
	if (!from && !to) return '';
	const year = from.slice(0, 4);
	if (from === `${year}-01-01` && to === `${year}-12-31`) return year;
	return `${from || '…'} – ${to || '…'}`;
}

/**
 * The filter button's label (the Django menu's filterLabel): the first active
 * filter, then "+N" for the others, or "All" when none is on.
 */
export function filterLabel(filters: LibraryFilters, options: LibraryFilterOptions): string {
	const labels: string[] = [];
	if (filters.rating && filters.rating !== 'all') labels.push(RATING_LABELS[filters.rating] ?? 'Rated');
	if (filters.collection && filters.collection !== 'all') {
		labels.push(COLLECTION_LABELS[filters.collection] ?? 'Collected');
	}
	if (filters.progress && filters.progress !== 'all') {
		labels.push(PROGRESS_LABELS[filters.progress] ?? 'Any Progress');
	}
	if (filters.genre) labels.push(filters.genre);
	if (filters.implied_genre) labels.push(`Implied: ${filters.implied_genre}`);
	if (filters.year) labels.push(filters.year === 'unknown' ? 'Unknown Year' : filters.year);
	const completed = completedLabel(filters, options);
	if (completed) labels.push(`Completed: ${completed}`);
	if (filters.release && filters.release !== 'all') {
		labels.push(RELEASE_LABELS[filters.release] ?? 'Released');
	}
	if (filters.source) labels.push(filters.source.toUpperCase());
	if (filters.media_status) labels.push(filters.media_status);
	if (options.show_languages && filters.language) labels.push(short(filters.language));
	if (options.show_countries && filters.country) labels.push(short(filters.country));
	if (options.show_platforms && filters.platforms.length) {
		const prefix = filters.platform_mode === 'not' ? '-' : '+';
		labels.push(prefix + filters.platforms.join(filters.platform_mode === 'and' ? ' & ' : ', '));
	}
	if (options.show_origins && filters.origin) labels.push(short(filters.origin));
	if (options.show_formats && filters.format) {
		labels.push(
			filters.format === 'ebook'
				? 'eBook'
				: filters.format.charAt(0).toUpperCase() + filters.format.slice(1)
		);
	}
	if (options.show_authors && filters.author) labels.push(filters.author);
	if (options.show_providers && filters.provider) labels.push(filters.provider);
	if (filters.tags.length) {
		const prefix = filters.tag_mode === 'not' ? '-' : '+';
		labels.push(prefix + filters.tags.join(filters.tag_mode === 'and' ? ' & ' : ', '));
	}
	if (labels.length === 0) return 'All';
	return labels.length === 1 ? labels[0] : `${labels[0]} +${labels.length - 1}`;
}

/** Whether any filter is on (the "All" row is then not the active one). */
export function hasFilters(filters: LibraryFilters, options: LibraryFilterOptions): boolean {
	return filterLabel(filters, options) !== 'All';
}

/** Options whose label contains the search, case-insensitively. */
export function matching<T extends { label: string }>(options: T[], search: string): T[] {
	const needle = search.trim().toLowerCase();
	return needle ? options.filter((option) => option.label.toLowerCase().includes(needle)) : options;
}

/** One value toggled in or out of a multi-value filter. */
export function toggled(values: string[], value: string): string[] {
	return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}
