import { error } from '@sveltejs/kit';
import type { HistoryScreen } from '#lib/history/types.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url }) => {
	// One call: the Django History page's own days for this URL's month,
	// page and filters (v2 P4-E).
	const response = await fetch(`${url.origin}/api/v1/history/screen/${url.search}`);
	if (!response.ok) error(response.status >= 500 ? 503 : response.status, 'History could not load.');
	return { screen: (await response.json()) as HistoryScreen };
};
