import { error } from '@sveltejs/kit';
import { studioApiPath, type StudioScreen } from '#lib/details/api.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, params }) => {
	const response = await fetch(`${url.origin}${studioApiPath(params.source, params.id)}`);
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'This page could not load.');
	}
	return { studio: (await response.json()) as StudioScreen };
};
