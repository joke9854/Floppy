import { error } from '@sveltejs/kit';
import type { DiscoverScreen } from '#lib/discover/types.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, depends }) => {
	depends('floppy:discover');
	// One call: the Django Discover page's own context (v2 P4-G). A
	// `media_type` saves the user's last Discover type, as on the page.
	const response = await fetch(`${url.origin}/api/v1/discover/screen/${url.search}`);
	if (!response.ok) error(response.status >= 500 ? 503 : response.status, 'Discover could not load.');
	return { screen: (await response.json()) as DiscoverScreen };
};
