import { loadEpisode } from '#lib/details/episodeLoad.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = ({ fetch, url, params }) =>
	loadEpisode(fetch, url, params, 'anime');
