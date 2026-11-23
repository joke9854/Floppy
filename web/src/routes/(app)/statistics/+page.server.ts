import { error } from '@sveltejs/kit';
import { screenQuery, type StatisticsScreen } from '#lib/statistics/types.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, depends }) => {
	depends('floppy:statistics');
	// One call: the Django Statistics page's own context (v2 P4-H) for the
	// range and compare. `media-type` stays in the browser, as on the page.
	const response = await fetch(`${url.origin}/api/v1/statistics/screen/${screenQuery(url.searchParams)}`);
	if (!response.ok) error(response.status >= 500 ? 503 : response.status, 'Statistics could not load.');
	return { screen: (await response.json()) as StatisticsScreen };
};
