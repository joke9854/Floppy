import type { components } from '#lib/api/client.ts';

export type LibraryScreen = components['schemas']['LibraryScreen'];
export type LibraryCard = components['schemas']['LibraryCard'];

/**
 * The Library's state lives in the URL, as on the Django page (sort,
 * direction, status, search and the filter menu's parameters), so reload,
 * back and shared links show the same list. Everything is passed to the API
 * unchanged except `layout`, which would overwrite the user's Django grid or
 * table choice (the web has the grid only so far), and `page`, which the
 * screen asks for itself as it scrolls.
 */
export function apiQuery(search: Iterable<[string, string]>, page?: number): string {
	const query = new URLSearchParams();
	for (const [key, value] of search) {
		if (key === 'layout' || key === 'page') continue;
		query.append(key, value);
	}
	if (page && page > 1) query.set('page', String(page));
	const text = query.toString();
	return text ? `?${text}` : '';
}

/** The API path for one page of a type's Library. */
export function libraryApiPath(
	mediaType: string,
	search: Iterable<[string, string]>,
	page?: number
): string {
	return `/api/v1/library/${encodeURIComponent(mediaType)}/${apiQuery(search, page)}`;
}

/**
 * The URL after one change: `null` removes the parameter. A new sort or
 * status starts the list again, so the page number never carries over.
 */
export function withParams(href: string, changes: Record<string, string | null>): string {
	const next = new URL(href);
	next.searchParams.delete('page');
	for (const [key, value] of Object.entries(changes)) {
		if (value === null) next.searchParams.delete(key);
		else next.searchParams.set(key, value);
	}
	return `${next.pathname}${next.search}`;
}
