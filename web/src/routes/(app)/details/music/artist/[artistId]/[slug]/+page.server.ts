import { error, redirect } from '@sveltejs/kit';
import { artistApiPath, type ArtistScreen } from '#lib/details/media.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, params }) => {
	// A redirect, a merge or a canonical move answers 400: the Django page follows it.
	const django = `/details/music/artist/${encodeURIComponent(params.artistId)}/${encodeURIComponent(params.slug)}/${url.search}`;
	const response = await fetch(`${url.origin}${artistApiPath(params.artistId)}`);
	if (response.status === 400) redirect(307, django);
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'This page could not load.');
	}
	return { screen: (await response.json()) as ArtistScreen };
};
