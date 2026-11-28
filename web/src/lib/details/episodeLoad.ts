import { error } from '@sveltejs/kit';
import { episodeApiPath, type EpisodeScreen } from '#lib/details/api.ts';

/** The episode page's loader, shared by the show and anime routes. */
export async function loadEpisode(
	fetch: typeof globalThis.fetch,
	url: URL,
	params: { source: string; id: string; season: string; episode: string },
	parent?: 'anime'
) {
	const response = await fetch(
		`${url.origin}${episodeApiPath(params.source, params.id, params.season, params.episode, parent)}`
	);
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'This episode could not load.');
	}
	return { episode: (await response.json()) as EpisodeScreen };
}
