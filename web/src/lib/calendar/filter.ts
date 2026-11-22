import type { components } from '#lib/api/client.ts';

export type CalendarScreen = components['schemas']['CalendarScreen'];
export type CalendarRelease = components['schemas']['CalendarRelease'];
export type FilterType = components['schemas']['CalendarFilterType'];

/**
 * The Calendar's type and status filter (P4-F), as the Django page's
 * calendarFilters(): kept in the browser under the page's own storage key,
 * so a filter set on either page holds on both.
 */
export type CalendarFilter = { selectedMediaTypes: string[]; selectedStatusesByType: Record<string, string[]> };

export const storageKey = (userId: number) => `yamtrack.calendar.filters.${userId}`;

const statusValues = (type: FilterType) => type.statuses.map((status) => status.value);

/** Every type and every status: the page's default. */
export function allOn(types: FilterType[]): CalendarFilter {
	return {
		selectedMediaTypes: types.map((type) => type.value),
		selectedStatusesByType: Object.fromEntries(
			types.filter((type) => type.statuses.length).map((type) => [type.value, statusValues(type)])
		)
	};
}

/** The saved filter merged into this month's options, as loadSavedFilters(). */
export function loadFilter(raw: string | null, types: FilterType[]): CalendarFilter {
	const filter = allOn(types);
	if (!raw) return filter;
	try {
		const saved = JSON.parse(raw) as Partial<CalendarFilter>;
		const valid = new Set(types.map((type) => type.value));
		if (Array.isArray(saved.selectedMediaTypes)) {
			filter.selectedMediaTypes = saved.selectedMediaTypes.filter((type) => valid.has(type));
		}
		if (saved.selectedStatusesByType && typeof saved.selectedStatusesByType === 'object') {
			const merged: Record<string, string[]> = {};
			for (const type of types) {
				const available = statusValues(type);
				const kept = saved.selectedStatusesByType[type.value];
				merged[type.value] = Array.isArray(kept) ? kept.filter((status) => available.includes(status)) : available;
			}
			filter.selectedStatusesByType = merged;
		}
	} catch {
		// A broken saved value keeps the default, as on the page.
	}
	return filter;
}

/** Whether a release shows under the filter (the page's filterReleaseMarkup). */
export function shows(release: CalendarRelease, filter: CalendarFilter): boolean {
	if (!filter.selectedMediaTypes.includes(release.media_type)) return false;
	const selected = filter.selectedStatusesByType[release.media_type] ?? [];
	return !release.status || selected.includes(release.status);
}

export function partialStatus(type: FilterType, filter: CalendarFilter): boolean {
	if (!type.statuses.length) return false;
	return (filter.selectedStatusesByType[type.value] ?? []).length !== type.statuses.length;
}

/** The filter button's words: All Types, No Types, one type, or N Types; " ·" for a status filter. */
export function filterLabel(types: FilterType[], filter: CalendarFilter): string {
	const marker = types.some((type) => filter.selectedMediaTypes.includes(type.value) && partialStatus(type, filter))
		? ' ·'
		: '';
	if (types.length > 0 && filter.selectedMediaTypes.length === types.length) return `All Types${marker}`;
	if (filter.selectedMediaTypes.length === 0) return 'No Types';
	if (filter.selectedMediaTypes.length === 1) {
		const only = types.find((type) => type.value === filter.selectedMediaTypes[0]);
		return only ? `${only.label}${marker}` : '1 Type';
	}
	return `${filter.selectedMediaTypes.length} Types${marker}`;
}

/** The iCal export link with its repeated media_types and status params. */
export function exportUrl(base: string, mediaTypes: string[], statuses: string[]): string {
	const params = new URLSearchParams();
	for (const type of mediaTypes) params.append('media_types', type);
	for (const status of statuses) params.append('status', status);
	const query = params.toString();
	return query ? `${base}?${query}` : base;
}
