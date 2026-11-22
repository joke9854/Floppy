import type { components } from '#lib/api/client.ts';

export type DiscoverScreen = components['schemas']['DiscoverScreen'];
export type DiscoverCard = components['schemas']['DiscoverScreenCard'];
export type DiscoverSlide = components['schemas']['DiscoverScreenSlide'];
export type DiscoverAction = components['schemas']['DiscoverScreenAction'];

/** The page's query for a type tab or the next rows, as the Django page writes it. */
export function discoverQuery(mediaType: string, showMore = false): string {
	const params = new URLSearchParams({ media_type: mediaType });
	if (showMore) params.set('show_more', '1');
	return `?${params}`;
}

/** The form fields a quick action posts to `/discover/action`. */
export function actionFields(action: 'planning' | 'dismiss', fields: DiscoverAction): Record<string, string> {
	return { action, ...fields, discover_debug: '0' };
}

export interface CacheStatus {
	exists?: boolean;
	is_stale?: boolean;
	is_refreshing?: boolean;
	refresh_scheduled?: boolean;
	recently_built?: boolean;
}

/** True while a cache-status answer says the rows are still rebuilding. */
export function stillRefreshing(status: CacheStatus): boolean {
	return Boolean(status.is_refreshing || status.refresh_scheduled);
}

/**
 * Whether the rebuild the page waits on is done, as the page decides it: a
 * manual Refresh needs fresh rows (built in the last minute, not stale); a
 * background rebuild only needs rows.
 */
export function rebuildDone(status: CacheStatus, manual: boolean): boolean {
	if (stillRefreshing(status) || !status.exists) return false;
	return manual ? Boolean(!status.is_stale && status.recently_built) : true;
}
