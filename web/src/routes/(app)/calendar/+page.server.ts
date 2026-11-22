import { error } from '@sveltejs/kit';
import type { CalendarScreen } from '#lib/calendar/filter.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url }) => {
	// One call: the Django Calendar page's own month (v2 P4-F). `view` saves
	// the user's layout, as on the page.
	const response = await fetch(`${url.origin}/api/v1/calendar/screen/${url.search}`);
	if (!response.ok) error(response.status >= 500 ? 503 : response.status, 'The Calendar could not load.');
	return { screen: (await response.json()) as CalendarScreen };
};
