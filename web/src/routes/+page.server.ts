import { error } from '@sveltejs/kit';
import { createApi } from '#lib/api/client.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url }) => {
	// Through the session bridge: Django's session-only account endpoint.
	const { data, response } = await createApi(fetch, url.origin).GET('/api/v1/user/account/');
	if (!data) error(response.status >= 500 ? 503 : response.status, 'Could not load your account.');
	return { account: data };
};
