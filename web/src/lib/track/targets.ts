import type { TrackTarget } from './open.svelte.ts';

/** Types the web dialog edits so far; the rest keep their Django page. */
export const TRACK_TYPES = new Set(['movie', 'tv', 'season', 'episode']);

const DETAIL = /^\/details\/([^/?#]+)\/(movie|tv)\/([^/?#]+)\/[^/?#]+\/?(?:\?season=(\d+))?$/;
const EPISODE = /^\/details\/([^/?#]+)\/tv\/([^/?#]+)\/[^/?#]+\/season\/(\d+)\/episode\/(\d+)\/?$/;

/**
 * The dialog target for a title's Django page URL (`media_url`): a movie or
 * show, a season (`?season=N` on a season card) or an episode. Null for
 * anything the web dialog does not edit yet.
 */
export function trackTargetFromUrl(url: string, mediaType?: string): TrackTarget | null {
	const episode = EPISODE.exec(url);
	if (episode) {
		const [, source, mediaId, season, number] = episode;
		return { mediaType: 'episode', source, mediaId, season: Number(season), episode: Number(number) };
	}
	const detail = DETAIL.exec(url);
	if (!detail) return null;
	const [, source, type, mediaId, season] = detail;
	if (mediaType === 'season' && season) {
		return { mediaType: 'season', source, mediaId, season: Number(season) };
	}
	return { mediaType: type, source, mediaId };
}
