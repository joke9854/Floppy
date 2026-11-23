import { error } from '@sveltejs/kit';
import { listsQuery, type ListsScreen } from '#lib/lists/types.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, depends }) => {
	depends('floppy:lists');
	// One call: the Django Lists page's own context (v2 P4-I1). A sort saves
	// the user's list sort, as on the page.
	const response = await fetch(`${url.origin}/api/v1/lists/screen/${listsQuery(url.searchParams)}`);
	if (!response.ok) error(response.status >= 500 ? 503 : response.status, 'Lists could not load.');
	return { screen: (await response.json()) as ListsScreen };
};
