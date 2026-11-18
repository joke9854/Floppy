import { error, redirect } from '@sveltejs/kit';
import { libraryApiPath, type LibraryScreen } from '#lib/library/query.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, params }) => {
	// One call: the Django Library page's own list for this type, with the
	// URL's sort, status, search and filters (the user's saved ones when the
	// URL has none). It saves a changed sort or status, as the page does.
	const response = await fetch(`${url.origin}${libraryApiPath(params.type, url.searchParams)}`);
	if (response.status === 400) {
		// No web Library for this type yet (music, podcasts, comics).
		redirect(307, `/medialist/${encodeURIComponent(params.type)}`);
	}
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'The Library could not load.');
	}
	return { screen: (await response.json()) as LibraryScreen };
};
