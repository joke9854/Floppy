import { error, redirect } from '@sveltejs/kit';
import { podcastApiPath, type PodcastScreen } from '#lib/details/media.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, params }) => {
	// A redirect, a merge or a canonical move answers 400: the Django page follows it.
	const django = `/details/${encodeURIComponent(params.source)}/podcast/${encodeURIComponent(params.id)}/` +
		`${encodeURIComponent(params.title ?? 'podcast')}${url.search}`;
	const response = await fetch(`${url.origin}${podcastApiPath(params.source, params.id)}`);
	if (response.status === 400) redirect(307, django);
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'This page could not load.');
	}
	return { screen: (await response.json()) as PodcastScreen };
};
