import { error } from '@sveltejs/kit';
import { createApi } from '#lib/api/client.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, depends }) => {
	depends('floppy:home');
	// One call: the Home sections, cached per user and day on the Django side.
	const { data, response } = await createApi(fetch, url.origin).GET('/api/v1/home/sections/');
	if (!data) error(response.status >= 500 ? 503 : response.status, 'Home could not load.');
	return { home: data };
};
