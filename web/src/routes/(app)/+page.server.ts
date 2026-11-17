import { error } from '@sveltejs/kit';
import { createApi } from '#lib/api/client.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, depends }) => {
	depends('floppy:home');
	const api = createApi(fetch, url.origin);
	// Both at once, no waterfall: the Home sections (cached per user and day
	// on the Django side) and Now Playing, which never fails the page.
	const [home, playing] = await Promise.all([
		api.GET('/api/v1/home/sections/'),
		api.GET('/api/v1/playback/now-playing/').catch(() => null)
	]);
	if (!home.data) {
		error(home.response.status >= 500 ? 503 : home.response.status, 'Home could not load.');
	}
	return { home: home.data, nowPlaying: playing?.data ?? { active: false } };
};
