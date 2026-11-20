import { error } from '@sveltejs/kit';
import { episodeApiPath, type EpisodeScreen } from '#lib/details/api.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, params }) => {
	const response = await fetch(
		`${url.origin}${episodeApiPath(params.source, params.id, params.season, params.episode)}`
	);
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'This episode could not load.');
	}
	return { episode: (await response.json()) as EpisodeScreen };
};
